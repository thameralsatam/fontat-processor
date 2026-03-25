from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.ttLib.tables.otTables import FeatureRecord, Feature
import io
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def freeze_features(font: TTFont, features_to_freeze: list) -> TTFont:
    """ حقن الميزات الاختيارية داخل ميزة rlig الإجبارية """
    if 'GSUB' not in font:
        return font
    
    gsub = font['GSUB'].table
    feature_list = gsub.FeatureList
    script_list = gsub.ScriptList
    lookups_to_inject = []
    feature_indices = []

    for i, rec in enumerate(feature_list.FeatureRecord):
        if rec.FeatureTag in features_to_freeze:
            feature_indices.append(i)
            for idx in rec.Feature.LookupListIndex:
                if idx not in lookups_to_inject:
                    lookups_to_inject.append(idx)

    if not lookups_to_inject:
        return font

    for script_rec in script_list.ScriptRecord:
        script = script_rec.Script
        langs = ([script.DefaultLangSys] if script.DefaultLangSys else [])
        langs += [ls.LangSys for ls in script.LangSysRecord]
        for lang in langs:
            if lang is None: continue
            rlig_idx = next((fi for fi in lang.FeatureIndex if feature_list.FeatureRecord[fi].FeatureTag == 'rlig'), None)
            
            if rlig_idx is not None:
                existing_lookups = feature_list.FeatureRecord[rlig_idx].Feature.LookupListIndex
                for idx in lookups_to_inject:
                    if idx not in existing_lookups: existing_lookups.append(idx)
            else:
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
    return font

@app.post("/convert")
async def convert_font(font: UploadFile = File(...), settings: str = Form(...)):
    try:
        data = json.loads(settings)
        requested_features = data.get("features", [])
        input_data = await font.read()
        var_font = TTFont(io.BytesIO(input_data))

        # 1. تثبيت المحاور المتغيرة (المصلحة والذكية)
        if 'fvar' in var_font:
            available_axes = {a.axisTag for a in var_font['fvar'].axes}
            location = {}
            for k, v in data.items():
                if k in available_axes:
                    try:
                        location[k] = float(v)
                    except: continue
            if location:
                try:
                    var_font = instancer.instantiateVariableFont(var_font, location)
                except Exception as e:
                    print(f"❌ Instancer Error: {e}")

        # 2. تجميد ميزات الأوبن تايب (التي كانت مفقودة في استدعائك الأخير)
        forbidden = {"init", "medi", "fina", "isol", "rlig", "calt", "ccmp", "mark", "mkmk"}
        if isinstance(requested_features, str):
            raw_list = requested_features.split(',')
        else:
            raw_list = requested_features

        features_to_freeze = list(set(f.strip() for f in raw_list if f.strip() and f.strip() not in forbidden))

        if features_to_freeze:
            var_font = freeze_features(var_font, features_to_freeze)

        # 3. الحفظ النهائي (BytesIO)
        output = io.BytesIO()
        var_font.save(output)
        return Response(
            content=output.getvalue(),
            media_type="font/ttf",
            headers={"Content-Disposition": "attachment; filename=fontat_fixed.ttf"}
        )

    except Exception as e:
        print(f"🔥 Error: {e}")
        return Response(content=json.dumps({"error": str(e)}), status_code=400)
