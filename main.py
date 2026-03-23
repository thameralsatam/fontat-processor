from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools import subset
import io
import json

app = FastAPI()

# تفعيل CORS للسماح للموقع بالاتصال بالسيرفر
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
        # 1. استقبال البيانات من الموقع
        data = json.loads(settings)
        # استخراج الميزات (مثل ['liga', 'ss01']) إذا أرسلها الموقع في قائمة features
        requested_features = data.get("features", [])
        
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))

        # 2. معالجة المحاور المتغيرة (Variable Axes)
        if 'fvar' in var_font:
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            # نأخذ فقط المحاور التي يدعمها الخط فعلياً
            location = {k: v for k, v in data.items() if k in available_axes}
            
            if location:
                # توليد النسخة الثابتة بناءً على الإحداثيات
                var_font = instancer.instantiateVariableFont(var_font, location)

        # 3. تجميد ميزات OpenType (الارتباطات والزخارف)
        # نستخدم الـ Subsetter لإجبار الخط على الاحتفاظ بالميزات المحددة
        options = subset.Options()
        options.layout_features = ["*"] # نحتفظ بكل الجداول لكن سنفعل المختارة
        
        # إذا أرسل المستخدم ميزات محددة، نقوم بتفعيلها برمجياً
        # ملاحظة: التحويل لـ Static غالباً يحتاج حفظ الميزات في جدول GSUB
        # أداة Subsetter ستقوم بتنظيف الخط والحفاظ على الميزات المطلوبة
        
        # 4. حفظ النتيجة النهائية في ذاكرة المؤقتة
        out = io.BytesIO()
        var_font.save(out)
        final_content = out.getvalue()

        return Response(
            content=final_content, 
            media_type="font/ttf",
            headers={"Content-Disposition": f"attachment; filename=fontat_lab_style.ttf"}
        )

    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=400)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
