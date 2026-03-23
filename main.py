from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools import subset  # استيراد أدوات القص والتجميد
import io
import json

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
        # 1. استخراج الميزات المطلوبة من الـ JSON المرسل
        requested_features = data.get("features", [])
        
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))

        # 2. تثبيت المحاور المتغيرة (wght, KASH, etc)
        if 'fvar' in var_font:
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            location = {k: v for k, v in data.items() if k in available_axes}
            if location:
                # تحويل الخط لنسخة ثابتة (Static) بناءً على المحاور
                var_font = instancer.instantiateVariableFont(var_font, location)

        # 3. 🔥 التعديل الجوهري: تجميد ميزات الـ OpenType
        # نستخدم Subsetter لإخبار الخط أن هذه الميزات يجب أن تصبح "دائمة"
        options = subset.Options()
        
        # تفعيل الميزات التي طلبها المستخدم + الميزات الأساسية للغة العربية
        # الميزات الأساسية مثل (ccmp, kern, mark, mkmk) ضرورية لسلامة الخط
        essential_arabic = ["ccmp", "kern", "mark", "mkmk", "init", "medi", "fina", "isol"]
        options.layout_features = list(set(requested_features + essential_arabic))
        
        # إعداد الـ Subsetter
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(glyphs=var_font.getGlyphOrder())
        subsetter.subset(var_font)

        # 4. حفظ النتيجة النهائية
        out = io.BytesIO()
        var_font.save(out)
        final_content = out.getvalue()

        return Response(
            content=final_content, 
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fixed_font.ttf"}
        )

    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
