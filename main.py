from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
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
        # 1. تحويل الإعدادات القادمة من الموقع إلى قاموس (Dictionary)
        target_settings = json.loads(settings)
        
        # 2. قراءة ملف الخط
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))
        
        # 3. التأكد أن الخط متغير أصلاً
        if 'fvar' not in var_font:
            # إذا لم يكن متغيراً، نرجعه كما هو كملف ثابت
            return Response(content=input_data, media_type="font/ttf")

        # 4. 🔥 الكود الذكي: استخراج المحاور الحقيقية الموجودة في الملف حالياً
        available_axes = {a.axisTag for a in var_font['fvar'].axes}
        
        # 5. تنقية الإعدادات: نأخذ فقط المحاور المشتركة بين (ما طلبه المستخدم) و (ما يدعمه الخط)
        # هذا السطر يمنع حدوث خطأ 'swsh' أو غيره للأبد
        final_location = {k: v for k, v in target_settings.items() if k in available_axes}

        # 6. إذا لم يكن هناك أي تطابق، نرجع الخط الأصلي
        if not final_location:
            out = io.BytesIO()
            var_font.save(out)
            return Response(content=out.getvalue(), media_type="font/ttf")

        # 7. توليد النسخة الثابتة بناءً على المحاور المتاحة فقط
        static_font = instancer.instantiateVariableFont(var_font, final_location)
        
        out = io.BytesIO()
        static_font.save(out)
        return Response(content=out.getvalue(), media_type="font/ttf")

    except Exception as e:
        # إرجاع رسالة خطأ واضحة في حال حدث شيء غير متوقع
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
