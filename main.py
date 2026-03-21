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

@app.get("/")
def read_root():
    return {"status": "Fontat Processor is Online"}

@app.post("/convert")
async def convert_font(
    font: UploadFile = File(...),
    # هنا استلمنا "كل الإعدادات" كـ نص JSON عشان نكون مرنين
    settings: str = Form(...) 
):
    try:
        target_settings = json.loads(settings)
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))
        
        # تنفيذ التعديل بناءً على كل المحاور المرسلة (wght, swsh, kash, etc.)
        static_font = instancer.instantiateVariableFont(var_font, target_settings)
        
        out = io.BytesIO()
        static_font.save(out)
        return Response(content=out.getvalue(), media_type="font/ttf")
    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
