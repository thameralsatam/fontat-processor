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

        # 2. حفظ الخط في ملف مؤقت
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttf") as tmp_in:
            var_font.save(tmp_in.name)
            tmp_in_path = tmp_in.name
            
        tmp_out_path = tmp_in_path.replace(".ttf", "_frozen.ttf")

        # 3. 🔥 التفعيل الذكي (Default Activation)
        # ميزات الربط العربي الأساسية + الميزات المطلوبة من المستخدم
        arabic_essentials = ["init", "medi", "fina", "isol", "rlig", "calt", "ccmp", "mark", "mkmk"]
        all_to_activate = list(set(requested_features + arabic_essentials))
        
        try:
            # بناء الأمر برمجياً:
            # نستخدم -o بدلاً من -f للحفاظ على ذكاء الميزة وسياقها
            command = [sys.executable, "-m", "pyftfeatfreeze"]
            
            for feat in all_to_activate:
                command.extend(["-o", feat]) # تفعيل الميزة كخيار افتراضي ذكي
            
            # إضافة براميتر الحفاظ على الجداول وملفات الدخل والخرج
            command.extend(["-r", tmp_in_path, tmp_out_path])
            
            subprocess.run(command, check=True, capture_output=True)
            
            with open(tmp_out_path, "rb") as f:
                final_content = f.read()
            if os.path.exists(tmp_out_path): os.remove(tmp_out_path)
            
        except Exception as e:
            # في حال الفشل نرجع الخط الثابت الأصلي لضمان استمرار الخدمة
            print(f"Freezing Error: {e}")
            with open(tmp_in_path, "rb") as f:
                final_content = f.read()

        if os.path.exists(tmp_in_path): os.remove(tmp_in_path)

        return Response(
            content=final_content, 
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fontat_pro.ttf"}
        )

    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
