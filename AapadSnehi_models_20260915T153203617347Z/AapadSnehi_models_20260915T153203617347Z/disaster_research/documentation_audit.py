"""Record locally verified schema/provenance details and source PDF excerpts."""
import json
from pypdf import PdfReader
import pandas as pd
from .paths import RAW,PROCESSED,REPORTS
from .flood_data import DYNAMIC,STATIC_FILES,SOURCE

def run():
    reader=PdfReader(RAW/"flood"/"00_CAMELS_IND_Data_Description.pdf")
    # Page references, not redistribution of the whole paper.
    page3=reader.pages[2].extract_text()
    units_verified="m3/s" in page3.replace(" ","")
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet")
    report={"streamflow_units_verified_in_local_description_page_3":units_verified,
      "forcing_summary_selected_rows":frame[DYNAMIC].agg(["min","max","count"]).to_dict(),
      "retained_static_columns_by_file":{name:pd.read_csv(SOURCE/"attributes_csv"/name).select_dtypes(include="number").columns.tolist() for name in STATIC_FILES},
      "static_caveat":"HWSD v2.0 (2023), HiHydroSoil v2.0 (2020), GLHYMPS (2014), GLiM (2012), GHI (2023), SRTM. Retrospective map properties; publication after historical dates precludes operational replay. Soil carbon/water table may change and should be removed or time-varying in operational validation.",
      "flood_dynamic_units":{"discharge":"m3/s","prcp(mm/day)":"mm/day","tavg(C)":"degrees Celsius","rel_hum(%)":"percent at 2 m", "sm_lvl1(kg/m2)":"kg/m2, 0-0.1 m layer","sm_lvl2(kg/m2)":"kg/m2, 0.1-0.35 m layer","sm_lvl3(kg/m2)":"kg/m2, 0.35-1 m layer","sm_lvl4(kg/m2)":"kg/m2, 1-3 m layer"},
      "flood_availability":"Daily IMD observations and retrospective IMDAA; publication timestamps absent. End of source day assumed as conceptual issue convention only; local/UTC aggregation not independently established.",
      "wildfire_units":{"elevation":"m","pdsi":"dimensionless drought index","NDVI":"scaled vegetation index, native integer scale","pr":"mm/day","sph":"kg/kg","th":"degrees clockwise from north","tmmn":"K","tmmx":"K","vs":"m/s","erc":"energy release component index","population":"people/km2","PrevFireMask":"-1 unknown, 0 inactive, 1 active"},
      "wildfire_availability":"Current-day satellite composite and aligned environmental layers, latest timestamps for slower products per paper. Per-channel actual release timestamps absent. No future realised weather is deliberately joined."}
    (REPORTS/"feature_units_and_availability.json").write_text(json.dumps(report,indent=2))
    manifest_path=REPORTS/"acquisition_manifest.json"
    manifest=json.loads(manifest_path.read_text())
    for record in manifest["records"]:
        if record["dataset"] in ["flood","wildfire"]:
            record["license"]="CC BY 4.0; retain attribution and review upstream conditions"
            record["terms_url"]="https://zenodo.org/records/14999580" if record["dataset"]=="flood" else "https://www.kaggle.com/datasets/fantineh/next-day-wildfire-spread"
    manifest_path.write_text(json.dumps(manifest,indent=2))

if __name__ == "__main__":run()
