from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
# التعديل هنا: استيراد الكلاسات من المسار العام للمكتبة
from fontTools.ttLib.tables.otTables import FeatureRecord, Feature
import io
import json

app = FastAPI()

# إعدادات الـ CORS لضمان اتصال الموقع بالسيرفر بدون مشاكل
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def freeze_features(font: TTFont, features_to_freeze: list) -> TTFont:
    """
    يحول الميزات الاختيارية المختارة إلى ميزة rlig التي تعمل تلقائياً على كل الأجهزة.
    """
    if 'GSUB' not in font:
        print("⚠️ No GSUB table found in font.")
        return font

    gsub = font['GSUB'].table
    feature_list = gsub.FeatureList
    script_list = gsub.ScriptList

    # اجمع تعليمات الميزات المطلوبة وأرقام مواقعها
    lookups_to_inject = []
    feature_indices = []

    for i, rec in enumerate(feature_list.FeatureRecord):
        if rec.FeatureTag in features_to_freeze:
            feature_indices.append(i)
            for idx in rec.Feature.LookupListIndex:
                if idx not in lookups_to_inject:
                    lookups_to_inject.append(idx)

    if not lookups_to_inject:
        print(f"⚠️ No lookups found for features: {features_to_freeze}")
        return font

    # لكل script/language يحتوي على الميزات المطلوبة، أضف تعليماتها لـ rlig
    for script_rec in script_list.ScriptRecord:
        script = script_rec.Script
        langs = ([script.DefaultLangSys] if script.DefaultLangSys else [])
        langs += [ls.LangSys for ls in script.LangSysRecord]

        for lang in langs:
            if lang is None:
                continue

            # تحقق إذا هذا الـ lang يستخدم أي من الميزات المطلوبة
            if not any(i in lang.FeatureIndex for i in feature_indices):
                continue

            # دور على rlig موجودة في هذا الـ lang
            rlig_idx = next(
                (fi for fi in lang.FeatureIndex
                 if feature_list.FeatureRecord[fi].FeatureTag == 'rlig'),
                None
            )

            if rlig_idx is not None:
                # أضف التعليمات للـ rlig الموجودة
                existing_lookups = feature_list.FeatureRecord[rlig_idx].Feature.LookupListIndex
                for idx in lookups_to_inject:
                    if idx not in existing_lookups:
                        existing_lookups.append(idx)
            else:
                # أنشئ rlig جديدة وأضفها
                new_feature = Feature()
                new_feature.FeatureParams = None
                new_feature.LookupListIndex = list(lookups_to_inject)

                new_record = FeatureRecord()
                new_record.FeatureTag = 'rlig'
                new_record.Feature = new_feature

                new_index = len(feature_list.FeatureRecord)
                feature_list.FeatureRecord.append(new_record)
                feature_list.FeatureCount = len(feature_list.FeatureRecord)
                lang.FeatureIndex.append(new_index)

    print(f"✅ Features {features_to_freeze} frozen successfully.")
    return font


@app.post("/convert")
async def convert_font(
    font: UploadFile = File(...),
    settings: str = Form(...)
):
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
                    
        # 2. تثبيت محاور الخط المتغير (Variable Font Axes) - النسخة المصلحة
        if 'fvar' in var_font:
            # نجلب أسماء المحاور الموجودة في الخط فعلياً
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            
            location = {}
            for k, v in data.items():
                # إذا كان المفتاح موجود في محاور الخط وهو ليس قائمة الميزات
                if k in available_axes:
                    try:
                        # تحويل القيمة لرقم عشري ضروري جداً لنجاح العملية
                        location[k] = float(v)
                    except:
                        continue
            
            if location:
                try:
                    print(f"Applying location: {location}") # عشان تشوفه في الـ Logs
                    var_font = instancer.instantiateVariableFont(var_font, location)
                except Exception as inst_e:
                    print(f"❌ Instancer Error: {inst_e}")

        # 4. حفظ الخط وإرساله
        output = io.BytesIO()
        var_font.save(output)
        final_content = output.getvalue()

        return Response(
            content=final_content,
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fontat_fixed.ttf"}
        )

    except Exception as e:
        print(f"🔥 Global Error: {e}")
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
