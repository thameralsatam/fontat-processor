from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
import io
import json
import tempfile
import subprocess
import os
import sys

app = FastAPI()

# إعدادات الـ CORS لضمان اتصال الموقع بالسيرفر بدون مشاكل
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/convert")
async def convert_font(
    font: UploadFile = File(...),
    settings: str = Form(...) 
):
    tmp_in_path = None
    tmp_out_path = None
    try:
        # 1. قراءة الإعدادات والميزات المطلوبة
        data = json.loads(settings)
        requested_features = data.get("features", [])
        
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))

        # 2. تثبيت محاور الخط المتغير (Variable Font Axes)
        if 'fvar' in var_font:
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            location = {k: v for k, v in data.items() if k in available_axes}
            if location:
                try:
                    var_font = instancer.instantiateVariableFont(var_font, location)
                except Exception as inst_e:
                    print(f"Instancer Warning: {inst_e}")

        # 3. حفظ الخط في ملف مؤقت لمعالجته
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttf") as tmp_in:
            var_font.save(tmp_in.name)
            tmp_in_path = tmp_in.name
            
        tmp_out_path = tmp_in_path.replace(".ttf", "_frozen.ttf")

        # 4. 🔥 تنفيذ تجميد الميزات (Feature Freezing)
        try:
            # ميزات الربط العربي الأساسية (نتجنب تجميدها لأنها تسبب خطأ وتعمل تلقائياً)
            forbidden_features = {"init", "medi", "fina", "isol", "rlig", "calt", "ccmp", "mark", "mkmk"}
            
            if isinstance(requested_features, str):
                raw_list = requested_features.split(',')
            else:
                raw_list = requested_features
                
            # تصفية الميزات (إبقاء الاختيارية مثل ss01, ss02 وحذف الأساسية والتكرار)
            features_to_freeze = [f.strip() for f in raw_list if f.strip() and f.strip() not in forbidden_features]
            features_to_freeze = list(set(features_to_freeze))
            
            if features_to_freeze:
                # استخدام الأمر المباشر مع الاختصارات الصحيحة المتوافقة مع السيرفر
                command = ["pyftfeatfreeze"]
                
                for feat in features_to_freeze:
                    command.extend(["-f", feat])
                
                # -n: لعدم تغيير اسم الخط الداخلي (No Rename)
                # -r: لإعادة ربط الميزات (Remap)
                command.extend(["-n", "-r", tmp_in_path, tmp_out_path])
                
                print(f"🚀 Executing Command: {' '.join(command)}")
                
                # تنفيذ العملية والتقاط النتيجة
                result = subprocess.run(command, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"❌ Tool Error: {result.stderr}")
                    final_path = tmp_in_path
                else:
                    print(f"✅ Success: Features {features_to_freeze} frozen.")
                    final_path = tmp_out_path if os.path.exists(tmp_out_path) else tmp_in_path
            else:
                print("⚠️ No optional features to freeze. Returning base font.")
                final_path = tmp_in_path

            with open(final_path, "rb") as f:
                final_content = f.read()

        except Exception as tool_e:
            print(f"❌ Subprocess Exception: {tool_e}")
            with open(tmp_in_path, "rb") as f:
                final_content = f.read()

        # 5. إرسال ملف الخط النهائي
        return Response(
            content=final_content, 
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fontat_fixed.ttf"}
        )

    except Exception as e:
        print(f"🔥 Global Error: {e}")
        return Response(content=json.dumps({"error": str(e)}), status_code=400)

    finally:
        # 6. تنظيف الملفات المؤقتة فوراً لضمان عدم امتلاء الذاكرة
        if tmp_in_path and os.path.exists(tmp_in_path):
            try: os.remove(tmp_in_path)
            except: pass
        if tmp_out_path and os.path.exists(tmp_out_path):
            try: os.remove(tmp_out_path)
            except: pass
    except Exception as e:
        print(f"🔥 Global Error: {e}")
        return Response(content=json.dumps({"error": str(e)}), status_code=400)

    finally:
        # 6. تنظيف الملفات المؤقتة من السيرفر
        if tmp_in_path and os.path.exists(tmp_in_path):
            try: os.remove(tmp_in_path)
            except: pass
        if tmp_out_path and os.path.exists(tmp_out_path):
            try: os.remove(tmp_out_path)
            except: pass
