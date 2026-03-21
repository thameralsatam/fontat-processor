from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.varLib import mutator
from fontTools.ttLib import TTFont
import io

app = FastAPI()

# هذا الجزء مهم جداً عشان يسمح لموقعك يتصل بالسيرفر بدون مشاكل أمنية (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "Font Processor is Running"}

@app.post("/convert")
async def convert_font(font: UploadFile = File(...), wght: float = Form(...)):
    try:
        # 1. قراءة الملف المرفوع وتحويله لنظام يفهمه بايثون
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))
        
        # 2. تحديد الإحداثيات (الوزن اللي اختاره المستخدم)
        location = {'wght': wght}
        
        # 3. عملية التحويل السحرية (instantiate) اللي بتحافظ على العربي
        static_font = mutator.instantiateVariableFont(var_font, location)
        
        # 4. حفظ النتيجة في ذاكرة مؤقتة
        out = io.BytesIO()
        static_font.save(out)
        
        # 5. إرسال الملف النهائي للمتصفح
        return Response(
            content=out.getvalue(),
            media_type="font/ttf",
            headers={"Content-Disposition": f"attachment; filename=fontat-static.ttf"}
        )
    except Exception as e:
        return {"error": str(e)}
