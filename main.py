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
        
# استبدل الجزء رقم 3 بهذا المنطق المطور
        # 3. 🔥 التفعيل الاحترافي (Smart Default Activation)
        # ميزات الربط العربي الأساسية
        arabic_essentials = ["init", "medi", "fina", "isol", "rlig", "calt", "ccmp", "mark", "mkmk"]
        
        try:
            # المنطق المتبع في GitHub لإجبار الميزات دون تخريب:
            # نستخدم -o (On) لتفعيل الميزة برمجياً داخل جدول الميزات (Feature List)
            # ونستخدم -r (Remap) لإعادة بناء خريطة المحارف
            
            command = [sys.executable, "-m", "pyftfeatfreeze"]
            
            # تفعيل ميزات المستخدم لتكون "ON" افتراضياً
            for feat in requested_features:
                command.extend(["-o", feat])
            
            # التأكد من بقاء ميزات العربي "ON" افتراضياً
            for feat in arabic_essentials:
                command.extend(["-o", feat])
            
            # إضافة الخيارات التقنية لضمان عدم حذف أي "Lookup" ذكي
            command.extend(["-r", "--no-rename", tmp_in_path, tmp_out_path])
            
            result = subprocess.run(command, check=True, capture_output=True)
            
            # فحص إذا كان هناك محتوى في الملف الناتج
            if os.path.exists(tmp_out_path) and os.path.getsize(tmp_out_path) > 0:
                with open(tmp_out_path, "rb") as f:
                    final_content = f.read()
            else:
                # إذا فشل التجميد، نعود للنسخة الثابتة الأصلية
                with open(tmp_in_path, "rb") as f:
                    final_content = f.read()
