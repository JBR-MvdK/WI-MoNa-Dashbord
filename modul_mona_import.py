# mona_import.py

import pandas as pd
from datetime import datetime


#=== Einlesen und Parsen der MoNa-Dateien ========================================================================
# ⤷ Zeilenweise Aufbereitung, Umwandlung der Spaltennamen, erste Typkonvertierung
# ⤷ Timestamp muss vorhanden sein, daher Drop von Zeilen ohne Zeitstempel


def parse_mona(files):
    all_data = []
    for file in files:
        lines = file.read().decode("utf-8").splitlines()
        cleaned = [line.strip().strip("\x02").strip("\x03").split("\t") for line in lines if line.strip()]
        all_data.extend(cleaned)

    columns = [
        "Datum", "Zeit", "Status", "RW_Schiff", "HW_Schiff",
        "RW_BB", "HW_BB", "RW_SB", "HW_SB", "Geschwindigkeit",
        "Kurs", "Balkentiefe", "Druck_Balken", "Zugkraft", "Düsenwinkel",
        "P1_Vakuum", "P1_Druck", "P1_Fluss", "P1_Drehzahl", "P1_Leistung",
        "P2_Vakuum", "P2_Druck", "P2_Fluss", "P2_Drehzahl", "P2_Leistung",
        "P3_Vakuum", "P3_Druck", "P3_Fluss", "P3_Drehzahl", "P3_Leistung",
        "P4_Vakuum", "P4_Druck", "P4_Fluss", "P4_Drehzahl", "P4_Leistung",
        "Pegel", "Pegelkennung", "Pegelstatus", "Tiefgang", "Tiefe_Echolot",
        "Temp_Balken", "Baggernummer", "Baggerfeld", "Abs_Balkentiefe", "Solltiefe_BB", "Solltiefe_SB"
    ]
    
    # --- DataFrame setzen ---
    df = pd.DataFrame(all_data, columns=columns)
    df['timestamp'] = pd.to_datetime(df['Datum'].astype(str) + df['Zeit'].astype(str), format="%Y%m%d%H%M%S", errors='coerce')
    df['Baggerfeld'] = df['Baggerfeld'].astype(str).str.strip('"')
    
    cols_to_convert = [
        "Status", "HW_BB", "RW_SB", "HW_SB", "RW_Schiff",
        "HW_Schiff", "Abs_Balkentiefe"
    ]
    df[cols_to_convert] = df[cols_to_convert].apply(pd.to_numeric, errors="coerce")
    
    for col in ["Solltiefe_BB", "Solltiefe_SB"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] == 999.0, col] = None  # falls 999 als Platzhalter drin ist
    
    df["Baggernummer"] = df["Baggernummer"].astype(str).str.strip()    
    df["Schiffsname"] = df["Baggernummer"].map({
        "131": "WID AKKE",
        "167": "WID AQUADELTA",
        "137": "WID JAN",
        "129": "WID MAASMOND"
    })

    return df.dropna(subset=['timestamp'])
