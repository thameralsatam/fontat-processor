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
    try:
        data = json.loads(settings)
        requested_features = data.get("features", [])
        
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))

        # 1. تثبيت المحاور المتغيرة (wght, KASH, etc)
        if 'fvar' in var_font:
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            location = {k: v for k, v in data.items() if k in available_axes}
            if location:
                var_font = instancer.instantiateVariableFont(var_font, location)

        # 2. حفظ الخط الثابت في ملف مؤقت عشان نقدر نمرره لأداة التجميد
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttf") as tmp_in:
            var_font.save(tmp_in.name)
            tmp_in_path = tmp_in.name
            
        tmp_out_path = tmp_in_path.replace(".ttf", "_frozen.ttf")

        # 3. 🔥 التجميد الفعلي (Feature Freezing)
        if requested_features:
            # تحويل قائمة الميزات لنص مفصول بفواصل (مثل: liga,ss01)
            features_str = ",".join(requested_features)
            
            try:
                # تشغيل أداة pyftfeatfreeze من داخل البايثون
                subprocess.run(
                    ["pyftfeatfreeze", "-f", features_str, tmp_in_path, tmp_out_path], 
                    check=True, 
                    capture_output=True
                )
                
                # قراءة الخط بعد التجميد
                with open(tmp_out_path, "rb") as f:
                    final_content = f.read()
                os.remove(tmp_out_path) # تنظيف
                
            except subprocess.CalledProcessError as e:
                # لو صار خطأ في التجميد، نرجع الخط بدون تجميد أحسن ما نعطي إيرور
                print("Freezing Error:", e.stderr.decode())
                with open(tmp_in_path, "rb") as f:
                    final_content = f.read()
        else:
            # إذا ما اختار ميزات، نرجع الخط كما هو
            with open(tmp_in_path, "rb") as f:
                final_content = f.read()

        # تنظيف الملف المؤقت الأول
        if os.path.exists(tmp_in_path):
            os.remove(tmp_in_path)

        # 4. إرسال الخط الجاهز للموقع
        return Response(
            content=final_content, 
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fontat_frozen.ttf"}
        )

    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
