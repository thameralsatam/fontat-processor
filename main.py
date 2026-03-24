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
        data = json.loads(settings)
        requested_features = data.get("features", [])
        
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))

        # 1. تثبيت المحاور المتغيرة
        if 'fvar' in var_font:
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            location = {k: v for k, v in data.items() if k in available_axes}
            if location:
                var_font = instancer.instantiateVariableFont(var_font, location)

        # 2. حفظ الخط في ملف مؤقت
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttf") as tmp_in:
            var_font.save(tmp_in.name)
            tmp_in_path = tmp_in.name
            
        tmp_out_path = tmp_in_path.replace(".ttf", "_frozen.ttf")

        # 3. 🔥 تنفيذ الميزات (الفلترة الذكية والتجميد الصحيح)
        try:
            # قائمة الميزات الأساسية التي "يمنع" تجميدها لأنها تسبب انهيار الأداة
            forbidden_features = {"init", "medi", "fina", "isol", "rlig", "calt", "ccmp", "mark", "mkmk"}
            
            # تحويل الميزات لقائمة وتأكيد أنها نصوص
            if isinstance(requested_features, str):
                raw_list = requested_features.split(',')
            else:
                raw_list = requested_features
                
            # الفلترة: نأخذ فقط الميزات الاختيارية (مثل ss01) ونمنع الأساسية
            features_to_freeze = [f.strip() for f in raw_list if f.strip() and f.strip() not in forbidden_features]
            features_to_freeze = list(set(features_to_freeze)) # إزالة التكرار
            
            if features_to_freeze:
                command = [sys.executable, "-m", "pyftfeatfreeze"]
                
                # إضافة كل ميزة بشكل منفصل (هنا السر عشان ما تضرب الأداة!)
                for feat in features_to_freeze:
                    command.extend(["-f", feat])
                
                # إضافة الخيارات التقنية ومسارات الملفات
                command.extend(["--no-rename", tmp_in_path, tmp_out_path])
                
                print(f"Executing: {' '.join(command)}") # لمراقبة الأمر في Logs ريندر
                
                result = subprocess.run(command, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"❌ Tool Error: {result.stderr}")
                    final_path = tmp_in_path
                else:
                    final_path = tmp_out_path if os.path.exists(tmp_out_path) else tmp_in_path
            else:
                print("⚠️ لا توجد ميزات اختيارية لتجميدها (تم تجاهل الميزات الأساسية).")
                final_path = tmp_in_path

            # قراءة الملف النهائي
            with open(final_path, "rb") as f:
                final_content = f.read()

        except Exception as e:
            print(f"❌ Error: {e}")
            with open(tmp_in_path, "rb") as f:
                final_content = f.read()

        # 4. إرسال الرد
        return Response(
            content=final_content, 
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fontat_fixed.ttf"}
        )

    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=400)

    finally:
        # 5. تنظيف السيرفر (مرة واحدة فقط وبشكل آمن)
        if tmp_in_path and os.path.exists(tmp_in_path):
            try: os.remove(tmp_in_path)
            except: pass
        if tmp_out_path and os.path.exists(tmp_out_path):
            try: os.remove(tmp_out_path)
            except: pass
