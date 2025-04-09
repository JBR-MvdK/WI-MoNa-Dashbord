#=== Berechnung der Solltiefe und Toleranzkorridore ==============================================================
# ⤷ Es wird entweder BB- oder SB-Wert verwendet (BB bevorzugt), gültig nur bei Status == 2
# ⤷ Danach werden obere und untere Toleranzgrenzen berechnet
# data_processing.py


import pandas as pd

def berechne_solltiefe(df, toleranz_oben, toleranz_unten):
    df = df.copy()
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    df["Solltiefe_BB"] = pd.to_numeric(df["Solltiefe_BB"], errors="coerce")
    df["Solltiefe_SB"] = pd.to_numeric(df["Solltiefe_SB"], errors="coerce")

    df.loc[df["Solltiefe_BB"] == 999, "Solltiefe_BB"] = None
    df.loc[df["Solltiefe_SB"] == 999, "Solltiefe_SB"] = None

    soll_raw = df["Solltiefe_BB"].combine_first(df["Solltiefe_SB"])

    df["Solltiefe"] = None
    df.loc[df["Status"] == 2, "Solltiefe"] = soll_raw[df["Status"] == 2].ffill()

    # Toleranzwerte berechnen – NUR wenn Solltiefe vorhanden
    df["Solltiefe_Oben"] = df["Solltiefe"] + toleranz_oben
    df["Solltiefe_Unten"] = df["Solltiefe"] - toleranz_unten

    df.loc[df["Status"] != 2, ["Solltiefe", "Solltiefe_Oben", "Solltiefe_Unten"]] = None

    return df
