import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import pydeck as pdk
import plotly.graph_objects as go
import io


#=== Einlesen und Parsen der MoNa-Dateien --> modul_mona_import.py ========================================================================
from modul_mona_import import parse_mona

#=== XML-Datei der Baggerfeldgrenzen (LandXML) parsen --> modul_baggerfelder_xml_import.py ===========================================
from modul_baggerfelder_xml_import import parse_baggerfelder

#=== Solltiefe berechnen --> modul_solltiefe_berechnen.py ===========================================================
from modul_solltiefe_berechnen import berechne_solltiefe

#=== Koordinatensystem erkennen --> modul_koordinatenerkennung.py ===========================================================
from modul_koordinatenerkennung import erkenne_koordinatensystem

#=== Passwort --> auth.py =========================================================
from auth import get_password  # oder wie dein Modul heißt

def check_password():
    def password_entered():
        if st.session_state["password"] == get_password():
            st.session_state["pass_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["pass_correct"] = False

    if "pass_correct" not in st.session_state:
        st.text_input("Bitte Passwort eintragen um Auswertetool zu nutzen!", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["pass_correct"]:
        st.text_input("Bitte Passwort eintragen um Auswertetool zu nutzen!", type="password", on_change=password_entered, key="password")
        st.error("Falsches Passwort")
        return False
    else:
        return True

# ⛔ STOP wenn nicht eingeloggt
if not check_password():
    st.stop()

# -------------------------------------------------------------------
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Daten')
    return output.getvalue()
    
st.set_page_config(page_title="WI-MoNa Dashboard - MvdK", layout="wide")
st.title("📈 WI-MoNa Dashboard - MvdK")

#=== Datei-Upload im Sidebar =====================================================================================
# ⤷ Auswahl mehrerer MoNa-Dateien (.txt) und genau einer XML-Datei (für Baggerfeldgrenzen)

st.sidebar.header("📂 Datei-Upload")
uploaded_mona_files = st.sidebar.file_uploader("MoNa-Dateien (.txt)", type=["txt"], accept_multiple_files=True)
uploaded_xml_files = st.sidebar.file_uploader("Baggerfeldgrenzen (XML mit Namespace)", type=["xml"], accept_multiple_files=True)
xml_status = st.sidebar.empty()

koordsys_status = st.sidebar.empty()  # <-- HIER DEFINIEREN!


#=== Zeitliche Lücken erkennen und segmentieren (für Linienunterbrechungen) ======================================
# ⤷ Wird z. B. für Spülbalken-Koordinaten und Toleranz-Korridore genutzt

def split_by_gap(df, max_gap_minutes=2):
    df = df.sort_values(by="timestamp")
    df["gap"] = df["timestamp"].diff().dt.total_seconds() > (max_gap_minutes * 60)
    df["segment"] = df["gap"].cumsum()
    return df
    
def split_korridor_by_gap(df, max_gap_minutes=3):
    df = df.sort_values("timestamp")
    df["gap"] = df["timestamp"].diff().dt.total_seconds() > (max_gap_minutes * 60)
    df["korridor_segment"] = df["gap"].cumsum()
    return df
 

#=== Daten laden und prüfen ======================================================================================
# ⤷ Wenn beide Dateien vorhanden sind, wird alles geladen und sofort analysiert

if uploaded_mona_files:
    df = parse_mona(uploaded_mona_files)
    
    # Baggerfeld "0" oder leer entfernen
    df = df[~df["Baggerfeld"].isin(["", "0"])]
    
  
    # Min und Max Zeit für den Zeitfilter-Slider
    min_time = df["timestamp"].min()
    max_time = df["timestamp"].max()

    # 🛠️ Konvertierung für Streamlit-Slider
    from datetime import datetime
    min_time = pd.to_datetime(min_time).to_pydatetime()
    max_time = pd.to_datetime(max_time).to_pydatetime()
    
    # Anzeige von Metainformationen über die geladenen Schiffe und Baggerfelder
    schiffe = df["Schiffsname"].dropna().unique()
    if len(schiffe) == 1:
        schiffsname_text = f"**Schiff:** **{schiffe[0]}**"
    elif len(schiffe) > 1:
        schiffsname_text = f"**Schiffe im Datensatz:** {', '.join(schiffe)}"
    else:
        schiffsname_text = "Keine bekannten Schiffsnamen gefunden."

    st.markdown(f"""{schiffsname_text}  
    **Zeitraum:** {df["timestamp"].min().date()} – {df["timestamp"].max().date()}  
    **Baggerfelder:** {", ".join(sorted(df["Baggerfeld"].unique()))}  
    **Datenpunkte:** {len(df)}""")

#=== Automatische Erkennung des Koordinatensystems (UTM, GK, RD) aus modul_koordinatenerkennung.py ========
# ⤷ Basierend auf RW-/HW-Werten; bei Unsicherheit kann manuell gewählt werden
    if 'df' in locals() and not df.empty:      # oder: if uploaded_mona_files:
        proj_system, epsg_code, auto_erkannt = erkenne_koordinatensystem(
            df, st=koordsys_status, sidebar=st.sidebar
        )

#=== Bedingungen / Parameter im Sidebar ==========================================================================
# ⤷ Konfiguration von Toleranzgrenzen zur Solltiefe und Maximalgeschwindigkeit (für spätere Filter/Visualisierung) 
# Aufklappbarer Bereich für die Toleranzeinstellungen in der Sidebar
    with st.sidebar.expander("⚙️ Toleranzeinstellungen"):
        toleranz_oben = st.slider("Obere Toleranz (m)", min_value=0.0, max_value=2.0, value=1.0, step=0.1)
        toleranz_unten = st.slider("Untere Toleranz (m)", min_value=0.0, max_value=2.0, value=0.5, step=0.1)
        max_geschwindigkeit = st.slider('Maximale Geschwindigkeit (in Knoten)', min_value=0.1, max_value=10.0, value=3.0, step=0.1)

    # Berechnung der Solltiefe und Toleranzkorridore
    df = berechne_solltiefe(df, toleranz_oben, toleranz_unten)  # Hier Toleranzen übergeben!

#=== Multi-Select für Baggerfelder hinzufügen ============================================================
    with st.sidebar.expander("🔎 Filter nach Baggerfeld"):
        baggerfeld_auswahl = st.multiselect(
            "Wähle Baggerfelder aus", 
            options=sorted(df["Baggerfeld"].unique()), 
            default=sorted(df["Baggerfeld"].unique())  # Standardmäßig alle Baggerfelder
        )


#=== XML-Datei der Baggerfeldgrenzen (LandXML) parsen ============================================================
# ⤷ baggerfelder_parser.py ---> Extrahiert Polygon-Koordinaten für jedes Baggerfeld – inkl. Namenszuweisung

    baggerfelder = []
    if uploaded_xml_files:
        for uploaded_xml in uploaded_xml_files:
            try:
                felder = parse_baggerfelder(uploaded_xml, epsg_code)
                baggerfelder.extend(felder)
            except Exception as e:
                st.sidebar.warning(f"{uploaded_xml.name} konnte nicht geladen werden: {e}")
    
        xml_status.success(f"{len(baggerfelder)} Baggerfelder geladen")


#=== Normalisierung der Rechtswerte (z. B. Entfernen der Zonenkennung bei UTM) ===================================
# ⤷ Wird auf alle relevanten Spalten angewendet (RW_Schiff, RW_BB, RW_SB)

    def normalisiere_rechtswert(wert):
        if proj_system == "UTM" and auto_erkannt and wert > 30_000_000:
            return wert - int(epsg_code[-2:]) * 1_000_000
        return wert

# anwenden auf relevante Spalten
    for col in ["RW_Schiff", "RW_BB", "RW_SB"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].apply(normalisiere_rechtswert)
        

#=== Zeit-Slider ============================================================

    from datetime import timedelta

    st.markdown("### 📅 Zeitfilter")

    zeitbereich = st.slider(
        "Zeitraum auswählen",
        min_value=min_time,
        max_value=max_time,
        value=(min_time, max_time),
        step=timedelta(minutes=5),  # ⏱️ Hier ist der Trick!
        format="DD.MM.YYYY HH:mm",
        label_visibility="collapsed"
    )

    # Datumsbereich anwenden
    # Anwenden des Zeit- und Baggerfeldfilters
    df_filtered = df[(df["timestamp"] >= zeitbereich[0]) & (df["timestamp"] <= zeitbereich[1])]
    if baggerfeld_auswahl:
        df_filtered = df_filtered[df_filtered["Baggerfeld"].isin(baggerfeld_auswahl)]


    # Tabs anzeigen
    tab1, tab2, tab3 = st.tabs(["📊 Zeitdiagramm", "🗺️ Kartenansicht", "🕒 Zeit-Auswertung"])
 
#=====================================================================================       
#==== Reiter - Diagramm ==============================================================
#=====================================================================================   

    with tab1:
        st.subheader("📊 Zeitdiagramm")
    
    # --- Werte, die im Diagramm angezeigt werden können ---
        auswahl = [ "Status", "Pegel", "P1_Fluss", "P2_Fluss", "P3_Fluss",  "Geschwindigkeit", "Abs_Balkentiefe"]  # Immer alle anzeigen
    
    # --- Farbdefinitionen für Kurven ---
        farben = {
            "Abs_Balkentiefe": "#2E8B57",  # gedecktes Grün
            "P1_Fluss": "#696969",         # Dunkelgrau
            "P2_Fluss": "#696969",         # Dunkelgrau
            "P3_Fluss": "#696969",         # Dunkelgrau
            "Pegel": "#4682B4",            # gedecktes Blau
            "Status": "#DAA520",            # gedecktes Gold
            "Geschwindigkeit": "#DAA520"   # gedecktes Gold
        }
    
    # --- Daten vorbereiten ---    
        # Zeitdiagramm mit Filter nach Zeit und Baggerfeld
        df_plot = berechne_solltiefe(df_filtered.copy(), toleranz_oben, toleranz_unten)
        df_plot["datetime"] = pd.to_datetime(df_plot["Datum"].astype(str) + df_plot["Zeit"].astype(str), format="%Y%m%d%H%M%S")
        df_plot = df_plot.sort_values(by="datetime").reset_index(drop=True)

        fig = go.Figure()
        achsenbereiche = {}
    
    # --- Normierung vorbereiten (gemeinsame Y-Achse) ---    
        shared_min, shared_max = None, None
        
        if "Abs_Balkentiefe" in auswahl:
            df_plot["Abs_Balkentiefe"] = pd.to_numeric(df_plot["Abs_Balkentiefe"], errors='coerce')
            df_plot.loc[df_plot["Abs_Balkentiefe"] == 999, "Abs_Balkentiefe"] = None
            shared_min = df_plot["Abs_Balkentiefe"].min()
            shared_max = df_plot["Abs_Balkentiefe"].max()
            padding = (shared_max - shared_min) * 0.1 if shared_max != shared_min else 1
            shared_min -= padding
            shared_max += padding
            
    # --- Normierte Werte für Toleranz-Korridor & Solltiefe (nur Status == 2) ---
        df_plot["Solltiefe_norm"] = None
        df_plot["Solltiefe_Oben_norm"] = None
        df_plot["Solltiefe_Unten_norm"] = None
    
        df_plot.loc[df_plot["Status"] == 2, "Solltiefe_norm"] = (
            (df_plot["Solltiefe"] - shared_min) / (shared_max - shared_min)
        )
    
        df_plot.loc[df_plot["Status"] == 2, "Solltiefe_Oben_norm"] = (
            (df_plot["Solltiefe_Oben"] - shared_min) / (shared_max - shared_min)
        )
    
        df_plot.loc[df_plot["Status"] == 2, "Solltiefe_Unten_norm"] = (
            (df_plot["Solltiefe_Unten"] - shared_min) / (shared_max - shared_min)
        )
    
    # --- Korridor vorbereiten (gefiltert auf Status == 2) ---
        if shared_min is not None and "Abs_Balkentiefe" in auswahl:
            
            korridor_df = df_plot[
                (df_plot["Status"] == 2) &
                df_plot["Solltiefe"].notna() &
                df_plot["Solltiefe_Oben"].notna() &
                df_plot["Solltiefe_Unten"].notna()
            ][["timestamp", "Solltiefe", "Solltiefe_Oben", "Solltiefe_Unten", "Solltiefe_Oben_norm", "Solltiefe_Unten_norm"]]
            
    # --- Alle Kurven aus "auswahl" zeichnen ---
        for col in auswahl:
            df_plot[col] = pd.to_numeric(df_plot[col], errors='coerce')
            df_plot.loc[df_plot[col] == 999, col] = None
            y = df_plot[col]
            
            # --- Normierung pro Achse (nur falls keine gemeinsame Normierung) ---
            if col in ["Solltiefe_BB", "Solltiefe_SB"] and shared_min is not None:
                y_min, y_max = shared_min, shared_max
            else:
                y_min, y_max = y.min(), y.max()
                padding = (y_max - y_min) * 0.1 if y_max != y_min else 1
                y_min -= padding
                y_max += padding
    
            farbe = farben.get(col, "black")
     
            # --- Sichtbarkeit beim ersten Laden ---     
            sichtbarkeit = {
                "Abs_Balkentiefe": True,
                "P1_Fluss": False,
                "P2_Fluss": False,
                "P3_Fluss": False,
                "Pegel": False,
                "Status": False,
                "Geschwindigkeit": False
            }
            
             # --- Labels für Legende & Tooltip ---
            label_map = {
               "Abs_Balkentiefe": "Absolute Balkentiefe [m]",
               "P1_Fluss": "Pumpe 1 - Durchfluss [m³/h]",
               "P2_Fluss": "Pumpe 2 - Durchfluss [m³/h]",
               "P3_Fluss": "Pumpe 3 - Durchfluss [m³/h]",
               "Pegel": "Pegel [m]",
               "Status": "Status",
               "Geschwindigkeit": "Geschwindigkeit [knt]"
           }
    
            # --- Plot-Trace hinzufügen ---
            fig.add_trace(go.Scatter(
                x=df_plot["timestamp"],
                y=(y - y_min) / (y_max - y_min),
                mode="lines",
                name=label_map.get(col, col),  # Lesbare Legende
                customdata=df_plot[[col]],     # Originalwert für Tooltip (als 2D)
                hovertemplate=f"{label_map.get(col, col)}: %{{customdata[0]:.2f}} <extra></extra>",
                line=dict(color=farbe), visible="legendonly" if not sichtbarkeit.get(col, True) else True
            ))
            
    # --- Korridor und Solltiefe-Linie einfügen ---
        if not korridor_df.empty:
            korridor_df = split_korridor_by_gap(korridor_df)
            
            # --- Korridor als Fläche ---
            for seg_id, segment in korridor_df.groupby("korridor_segment"):
                x_korridor = pd.concat([segment["timestamp"], segment["timestamp"][::-1]])
                y_korridor = pd.concat([
                    segment["Solltiefe_Oben_norm"],
                    segment["Solltiefe_Unten_norm"][::-1]
                ])
    
                fig.add_trace(go.Scatter(
                    x=x_korridor,
                    y=y_korridor,
                    fill="toself",
                    fillcolor="rgba(178,34,34,0.1)",
                    line=dict(color="rgba(0,0,0,0)"),
                    hoverinfo="skip",
                    showlegend=(seg_id == 0),  # nur 1x Legende
                    name="Toleranz-Korridor",
                    visible=True
                ))
    
            # --- Solllinie als gepunktete Linie ---
            fig.add_trace(go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["Solltiefe_norm"],
                mode="lines",
                name="Solltiefe [m]",
                line=dict(color="firebrick", width=2, dash="dot"),
                hovertemplate="Solltiefe [m]: %{customdata[0]:.2f} <extra></extra>",
                customdata=df_plot[["Solltiefe"]],
                showlegend=True,
                visible=True,
                connectgaps=False
            ))
    
        else:
            st.info("ℹ️ Kein gültiger Toleranz-Korridor für den Plot vorhanden.")
    
    # --- Layout Einstellungen für Diagramm ---
        fig.update_layout(
            height=800,
            yaxis=dict(
                showticklabels=False,
                showgrid=True,
                tickvals=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                gridcolor="lightgray"
            ),
            hovermode="x unified",
            showlegend=True,
            legend=dict(orientation="v", x=1.02, y=1)
        )
        
    # --- Plot darstellen ---
        st.plotly_chart(fig, use_container_width=True)
    
        pass
     
       
#=====================================================================================       
#==== Interaktive Plotly-Kartenansicht (Mapbox / OSM) ================================
# ⤷ Zeigt die Positionen von Schiff, Spülbalken BB/SB auf einer interaktiven Karte mit Zeit-Tooltips
#=====================================================================================
    with tab2:
        import plotly.graph_objects as go
        from pyproj import Transformer
        
        st.subheader("🗺️ Interaktive Kartenansicht")
        
        # --- Überprüfen, ob die Daten existieren und nicht leer sind
        if 'df' in globals() and not df.empty:
        
            # --- Koordinatentransformation vorbereiten: Lokales Koordinatensystem → WGS84 (für Mapbox)
            transformer = Transformer.from_crs(epsg_code, "EPSG:4326", always_xy=True)
        
            # --- Filterung der gültigen Datenpunkte (Status == 2) mit vorhandenen Koordinaten für BB und SB
            bb_valid = df_filtered[(df_filtered["Status"] == 2) & df_filtered["RW_BB"].notna() & df_filtered["HW_BB"].notna()]
            bb_valid = split_by_gap(bb_valid)
            bb_valid = bb_valid.sort_values(by="timestamp")
            
            sb_valid = df_filtered[(df_filtered["Status"] == 2) & df_filtered["RW_SB"].notna() & df_filtered["HW_SB"].notna()]
            sb_valid = split_by_gap(sb_valid)
            sb_valid = sb_valid.sort_values(by="timestamp")
        
            # --- Separat: Schiff mit Status == 1 (für graue Verlaufslinie)
            ship_valid = df_filtered[(df_filtered["Status"] == 1)].dropna(subset=["RW_Schiff", "HW_Schiff"])
            ship_valid = ship_valid.sort_values(by="timestamp")
        
            # --- Transformation der Original-Koordinaten (RW/HW) in Längen-/Breitengrade
            bb_coords = bb_valid.apply(lambda row: transformer.transform(row["RW_BB"], row["HW_BB"]), axis=1)
            sb_coords = sb_valid.apply(lambda row: transformer.transform(row["RW_SB"], row["HW_SB"]), axis=1)
            ship_coords = ship_valid.apply(lambda row: transformer.transform(row["RW_Schiff"], row["HW_Schiff"]), axis=1)
           
            bb_lons, bb_lats = zip(*bb_coords) if not bb_coords.empty else ([], [])
            sb_lons, sb_lats = zip(*sb_coords) if not sb_coords.empty else ([], [])
            ship_lons, ship_lats = zip(*ship_coords) if not ship_coords.empty else ([], [])
            
            # --- Tooltip-Textfunktion
            def format_tooltip(row, soll_key):
                zeit = row["timestamp"].strftime("%d.%m.%Y - %H:%M:%S")
                tooltip = f"🕒 {zeit}"
        
                if row["Status"] == 2:
                    tiefe = row["Abs_Balkentiefe"]
                    tooltip += f"<br>📉 Tiefe: {tiefe} m"
        
                    soll = row[soll_key]
                    if soll != 999:
                        tooltip += f"<br>📐 Soll: {soll} m"
        
                geschwindigkeit = row.get("Geschwindigkeit", None)
                if pd.notna(geschwindigkeit):
                    tooltip += f"<br>🚤 Geschwindigkeit: {geschwindigkeit} knt"
        
                return tooltip
                
            # --- Tooltip-Daten für BB, SB und Schiff vorbereiten
            bb_text = bb_valid.apply(lambda row: format_tooltip(row, "Solltiefe_SB"), axis=1)
            sb_text = sb_valid.apply(lambda row: format_tooltip(row, "Solltiefe_SB"), axis=1)
            ship_text = ship_valid.apply(lambda row: format_tooltip(row, "Solltiefe_SB"), axis=1)
             
            # --- Plotly-Kartenansicht initialisieren
            fig_map = go.Figure()
        
            # --- Spülbalken BB auf der Karte darstellen
            for seg_id, segment_df in bb_valid.groupby("segment"):
                bb_coords = segment_df.apply(lambda row: transformer.transform(row["RW_BB"], row["HW_BB"]), axis=1)
                bb_lons, bb_lats = zip(*bb_coords)
                bb_text = segment_df.apply(lambda row: format_tooltip(row, "Solltiefe_BB"), axis=1)
        
                fig_map.add_trace(go.Scattermapbox(
                    lon=bb_lons,
                    lat=bb_lats,
                    mode="lines+markers",
                    line=dict(color="green", width=2),
                    marker=dict(size=6, color='green'),
                    name="Spülbalken BB" if seg_id == 0 else None,
                    showlegend=(seg_id == 0),
                    text=bb_text,
                    hoverinfo="text"
                ))
        
            # --- Spülbalken SB auf der Karte darstellen
            for seg_id, segment_df in sb_valid.groupby("segment"):
                sb_coords = segment_df.apply(lambda row: transformer.transform(row["RW_SB"], row["HW_SB"]), axis=1)
                sb_lons, sb_lats = zip(*sb_coords)
                sb_text = segment_df.apply(lambda row: format_tooltip(row, "Solltiefe_SB"), axis=1)
        
                fig_map.add_trace(go.Scattermapbox(
                    lon=sb_lons,
                    lat=sb_lats,
                    mode="lines+markers",
                    line=dict(color="red", width=2),
                    marker=dict(size=6, color='red'),
                    name="Spülbalken SB" if seg_id == 0 else None,
                    showlegend=(seg_id == 0),
                    text=sb_text,
                    hoverinfo="text"
                ))
        
            # --- Schiff auf der Karte darstellen
            fig_map.add_trace(go.Scattermapbox(
                lon=ship_lons,
                lat=ship_lats,
                mode='markers+lines',
                marker=dict(size=4, color='gray'),
                name='Schiff',
                text=ship_text,
                hoverinfo='text'
            ))
        
            # --- Karten-Zentrierung auf Basis der vorhandenen Daten
            center_lat = (bb_lats or sb_lats or ship_lats or [53.55])[0]
            center_lon = (bb_lons or sb_lons or ship_lons or [9.99])[0]
        
            # --- Layout der Karte anpassen (Zoom, Beschriftung, etc.)
            fig_map.update_layout(
                mapbox_style="open-street-map",  # oder open-street-map etc.
                mapbox_zoom=13,
                mapbox_center={
                    "lat": center_lat,
                    "lon": center_lon
                    
                },
                margin={"r": 0, "t": 0, "l": 0, "b": 0},
                height=800,
                hovermode="closest",
                legend=dict(
                    x=0.01,
                    y=0.99,
                    bgcolor="rgba(255,255,255,0.85)",
                    bordercolor="gray",
                    borderwidth=1
                )
            )
        # --- Baggerfelder aus XML in Karte darstellen (legendgesteuert)
        
        if 'baggerfelder' in locals() and baggerfelder:
            for idx, feld in enumerate(baggerfelder):
                coords = list(feld["polygon"].exterior.coords)
                lons, lats = zip(*coords)
                tooltip = f"Baggerfeld {feld['name']}<br>Solltiefe: {feld['solltiefe']} m"
        
                # Polygon-Umriss + Marker
                fig_map.add_trace(go.Scattermapbox(
                    lon=lons,
                    lat=lats,
                    mode="lines+markers",
                    fill="toself",
                    fillcolor="rgba(50, 90, 150, 0.2)",
                    line=dict(color="rgba(30, 60, 120, 0.8)", width=2),
                    marker=dict(size=3, color="rgba(30, 60, 120, 0.8)"),
                    name="Baggerfelder" if idx == 0 else None,
                    legendgroup="baggerfelder",
                    showlegend=(idx == 0),
                    visible=True,
                    text=[tooltip] * len(lons),
                    hoverinfo="text"
                ))
        
            # Zusätzlich: unsichtbarer Tooltip-Punkt in der Mitte der Fläche
                centroid = feld["polygon"].centroid
                lon_c, lat_c = centroid.x, centroid.y
                fig_map.add_trace(go.Scattermapbox(
                    lon=[lon_c],
                    lat=[lat_c],
                    mode="markers",
                    marker=dict(size=1, color="rgba(0,0,0,0)"),
                    text=[tooltip],
                    hoverinfo="text",
                    showlegend=False
                ))
                
        # --- Karte im Streamlit anzeigen
        st.plotly_chart(fig_map, use_container_width=True, config={"scrollZoom": True})
                
        pass
        
#=====================================================================================       
#==== Reiter - Zeit-Auswertung =======================================================
#=====================================================================================

    with tab3:

        with st.sidebar.expander(" ⚙️ Zeit-Auswertung"):
            anzeigeformat = st.selectbox(
                "Zeitformat für Zeitspalten",
                ["hh:mm:ss", "Dezimalstunden"],
                index=1
            )
            
            position_ausserhalb_aktiv = st.checkbox('Positionen außerhalb des Baggerfeldes', value=True)
            obere_toleranz_aktiv = st.checkbox('Obere Toleranz', value=True)
            untere_toleranz_aktiv = st.checkbox('Untere Toleranz', value=True)
            geschwindigkeit_aktiv = st.checkbox('Geschwindigkeit', value=True)

       
    
        df_filtered["Solltiefe_BB"] = pd.to_numeric(df_filtered["Solltiefe_BB"], errors="coerce")
        df_filtered["Solltiefe_SB"] = pd.to_numeric(df_filtered["Solltiefe_SB"], errors="coerce")

        from datetime import timedelta
        
        def to_hhmmss(td):
            try:
                if pd.isnull(td):
                    return "-"
                total_seconds = int(td.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                return f"{hours:02}:{minutes:02}:{seconds:02}"
            except Exception:
                return "-"

        def to_dezimalstunden(td):
            try:
                if pd.isnull(td):
                    return "-"
                return round(td.total_seconds() / 3600, 3)
            except:
                return "-"    
        
            
        if not (position_ausserhalb_aktiv or obere_toleranz_aktiv or untere_toleranz_aktiv or geschwindigkeit_aktiv):
            st.info("ℹ️ Es sind keine Fehlerbedingungen aktiv – es werden nur die reinen Baggerzeiten ausgewertet.")

                
   # Fehlerlogik & Filter – immer ausführen - ein Datenpunkt kann nur "einmal" fehlerhaft sein
   #===========================================================================================
 
        df_filtered["timestamp"] = pd.to_datetime(df_filtered["timestamp"], errors="coerce")
        
        
        fehler_daten = []
        fehler_zeiträume = []
        gueltige_zeilen = []
        
        if position_ausserhalb_aktiv or obere_toleranz_aktiv or untere_toleranz_aktiv or geschwindigkeit_aktiv:
            for _, row in df_filtered.iterrows():
                grund = None
                bnr = row["Baggerfeld"]
                timestamp = row["timestamp"]
        
                if position_ausserhalb_aktiv and row["Status"] == 2 and (
                    pd.isna(row["Solltiefe_BB"]) or pd.isna(row["Solltiefe_SB"])
                ):
                    grund = "Position"
        
                if grund is None and obere_toleranz_aktiv:
                    if pd.notna(row["Abs_Balkentiefe"]) and pd.notna(row["Solltiefe"]):
                        if row["Abs_Balkentiefe"] > row["Solltiefe"] + toleranz_oben:
                            grund = "Obere Toleranz"
        
                if grund is None and untere_toleranz_aktiv:
                    if pd.notna(row["Abs_Balkentiefe"]) and pd.notna(row["Solltiefe"]):
                        if row["Abs_Balkentiefe"] < row["Solltiefe"] - toleranz_unten:
                            grund = "Untere Toleranz"
        
                if grund is None and geschwindigkeit_aktiv:
                    if row["Status"] == 2:
                        if pd.isna(row["Geschwindigkeit"]) or pd.to_numeric(row["Geschwindigkeit"], errors="coerce") > max_geschwindigkeit:
                            grund = "Geschwindigkeit"
        
                if grund:
                    fehler_zeiträume.append({
                        "timestamp": timestamp,
                        "Baggerfeld": bnr,
                        "Fehlgrund": grund
                    })
                    fehler_daten.append([bnr, grund])
                else:
                    gueltige_zeilen.append(row)
        else:
            
      # Wenn keine Fehlerprüfung aktiv → einfach alle Datenpunkte mit Status==2 nehmen
            gueltige_zeilen = df_filtered[df_filtered["Status"] == 2].to_dict(orient="records")
            
      # Gültige Datenframe für weitere Auswertungen
        df_gueltig = pd.DataFrame(gueltige_zeilen)
        df_gueltig = df_gueltig[df_gueltig["Status"] == 2]
        
      # Fehlerzeiträume gruppieren 
        df_fehler = pd.DataFrame(fehler_zeiträume)
        if not df_fehler.empty and "timestamp" in df_fehler.columns:
            df_fehler.sort_values(by="timestamp", inplace=True)
        
        gruppen = []
        if not df_fehler.empty:
            
            start = df_fehler.iloc[0]["timestamp"]
            end = start
            current_grund = df_fehler.iloc[0]["Fehlgrund"]
            current_baggerfeld = df_fehler.iloc[0]["Baggerfeld"]
            anzahl = 1  # Startwert für die Zählung im ersten Fehlerzeitraum
            for i in range(1, len(df_fehler)):
                row = df_fehler.iloc[i]
                if (
                    row["Fehlgrund"] == current_grund and
                    row["Baggerfeld"] == current_baggerfeld and
                    (row["timestamp"] - end).total_seconds() <= 15
                ):
                    end = max(end, row["timestamp"])  # Absicherung bei gleichen Zeiten
                    anzahl += 1  # ← NEU: erhöhen
                else:
                    gruppen.append({
                        "Baggerfeld": current_baggerfeld,
                        "Startzeit": start,
                        "Endzeit": end,
                        "Dauer_raw": timedelta(seconds=anzahl * 10),
                        "Dauer": (
                            to_dezimalstunden(timedelta(seconds=anzahl * 10))
                            if anzeigeformat == "Dezimalstunden"
                            else to_hhmmss(timedelta(seconds=anzahl * 10))
                        ),
                        "Anzahl": anzahl,
                        "Fehlgrund": current_grund
                    })
                    # Reset
                    start = row["timestamp"]
                    end = start
                    current_grund = row["Fehlgrund"]
                    current_baggerfeld = row["Baggerfeld"]
                    anzahl = 1  # ← NEU: zurücksetzen

        
      # Letzten Abschnitt anhängen
            gruppen.append({
                "Baggerfeld": current_baggerfeld,
                "Startzeit": start,
                "Endzeit": end,
                "Dauer_raw": timedelta(seconds=anzahl * 10),
                "Dauer": (
                    to_dezimalstunden(timedelta(seconds=anzahl * 10))
                    if anzeigeformat == "Dezimalstunden"
                    else to_hhmmss(timedelta(seconds=anzahl * 10))
                ),
                "Anzahl": anzahl,
                "Fehlgrund": current_grund
            })
        


   #=== Ausgabe der Baggerzeiten je Baggerfeld           
   #===================================================================================== 
  
            
        st.markdown("<h3 style='font-size: 24px'>⏱️ Baggerzeiten je Baggerfeld</h3>", unsafe_allow_html=True)
    
        if not df_gueltig.empty:
            zeitraum_df = df_gueltig.groupby("Baggerfeld")["timestamp"].agg(["min", "max"]).reset_index()
            zeitraum_df["Anzahl gültiger Zeilen"] = df_gueltig.groupby("Baggerfeld").size().values
            zeitraum_df["delta"] = zeitraum_df["Anzahl gültiger Zeilen"] * 10  # in Sekunden
            zeitraum_df["delta"] = pd.to_timedelta(zeitraum_df["delta"], unit="s")                
            
            zeitraum_df["Gesamtdauer"] = zeitraum_df["delta"].apply(
                lambda td: to_dezimalstunden(td) if anzeigeformat == "Dezimalstunden" else to_hhmmss(td)
            )
            fehler_df = pd.DataFrame(fehler_daten, columns=["Baggerfeld", "Fehler"])
            fehler_matrix = pd.crosstab(fehler_df["Baggerfeld"], fehler_df["Fehler"]).reset_index()
    
            spalten_reihenfolge = ["Position", "Obere Toleranz", "Untere Toleranz", "Geschwindigkeit"]
            for spalte in spalten_reihenfolge:
                if spalte not in fehler_matrix.columns:
                    fehler_matrix[spalte] = 0
            fehler_matrix = fehler_matrix[["Baggerfeld"] + spalten_reihenfolge]
            fehler_matrix["Anzahl"] = fehler_matrix[spalten_reihenfolge].sum(axis=1)
            fehler_matrix["Verworfen (Sekunden)"] = fehler_matrix["Anzahl"] * 10
            
            fehler_matrix["Dauer korrigiert"] = (
                zeitraum_df["delta"] - pd.to_timedelta(fehler_matrix["Verworfen (Sekunden)"], unit="s")
            ).apply(
                lambda td: to_dezimalstunden(td) if anzeigeformat == "Dezimalstunden" else to_hhmmss(td)
            )
                            
            # Zeitverlust
            fehler_matrix["Zeitverlust"] = fehler_matrix["Verworfen (Sekunden)"].apply(
                lambda x: to_dezimalstunden(timedelta(seconds=int(x))) if anzeigeformat == "Dezimalstunden" else to_hhmmss(timedelta(seconds=int(x)))
            )
    
            zeitraum_df.rename(columns={"min": "Beginn", "max": "Ende", "Baggerfeld": "Baggerfeld"}, inplace=True)
            fehler_matrix.rename(columns={"Baggerfeld": "Baggerfeld"}, inplace=True)
    
            result = pd.merge(zeitraum_df[["Baggerfeld", "Beginn", "Ende", "Gesamtdauer"]], fehler_matrix, on="Baggerfeld", how="left").fillna(0)
    
            final_order = ["Baggerfeld", "Beginn", "Ende", "Gesamtdauer", "Dauer korrigiert", "Zeitverlust", "Anzahl"] + spalten_reihenfolge
        # Summen berechnen
            summen = {}
            
        # Zeitfelder in Sekunden
        # Gesamtdauer stammt aus zeitraum_df["delta"]
            gesamt_zeit = zeitraum_df["delta"].sum()
            
        #verworfen = Anzahl * 10 Sek
        #verworfen = result["Anzahl"].iloc[:-1].sum() * 10  # Letzte Zeile (Σ) nicht doppelt zählen!
            verworfen = len(fehler_daten) * 10
            delta_korrigiert = gesamt_zeit - timedelta(seconds=int(verworfen))
            
            summen["Gesamtdauer"] = (
                to_dezimalstunden(gesamt_zeit) if anzeigeformat == "Dezimalstunden" else to_hhmmss(gesamt_zeit)
            )
            summen["Dauer korrigiert"] = (
                to_dezimalstunden(delta_korrigiert) if anzeigeformat == "Dezimalstunden" else to_hhmmss(delta_korrigiert)
            )
            summen["Zeitverlust"] = (
                to_dezimalstunden(timedelta(seconds=int(verworfen)))
                if anzeigeformat == "Dezimalstunden"
                else to_hhmmss(timedelta(seconds=int(verworfen)))
            )
            
        # Zahlenspalten summieren
            summen["Anzahl"] = result["Anzahl"].sum()
            for feld in ["Position", "Obere Toleranz", "Untere Toleranz", "Geschwindigkeit"]:
                summen[feld] = result[feld].sum() if feld in result.columns else 0
            
        # Dummy-Felder
            summen["Baggerfeld"] = "Σ"
            summen["Beginn"] = "-"
            summen["Ende"] = "-"
            
        # Reihenfolge einhalten
            summenzeile = pd.DataFrame([summen])[final_order]
            
        # Neue Tabelle mit Summenzeile
            result_mit_summe = pd.concat([result[final_order], summenzeile], ignore_index=True)
            
        # Tabelle mit Summenzeile anzeigen
            st.dataframe(result_mit_summe, use_container_width=True, hide_index=True)                
      
        # Export nach Excel 
            excel_data_2 = convert_df_to_excel(result_mit_summe)
            st.download_button(
                label="📥 Baggerzeiten als Excel herunterladen",
                data=excel_data_2,
                file_name="baggerzeiten.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
   #=== Ausgabe der Summen (Gesamtdauer, Gesamtdauer korrigiert, Zeitverlust)       
   #===================================================================================== 
           
        st.markdown("---")     
        st.markdown("<h3 style='font-size: 24px'>🧾 Zusammenfassung</h3>", unsafe_allow_html=True)

        
        zeit_summen_df = pd.DataFrame([
            {
                "Kategorie": "Gesamtdauer",
                "Zeit": summen["Gesamtdauer"]
            },
            {
                "Kategorie": "Dauer korrigiert",
                "Zeit": summen["Dauer korrigiert"]
            },
            {
                "Kategorie": "Zeitverlust",
                "Zeit": summen["Zeitverlust"]
            }
        ])
        
        st.dataframe(zeit_summen_df, use_container_width=True, hide_index=True)                
        
        fehler_df = pd.DataFrame(fehler_daten, columns=["Baggerfeld", "Fehler"])
        fehler_counts = fehler_df["Fehler"].value_counts().rename_axis("Fehlerbedingung").reset_index(name="Anzahl")
        fehler_counts["Zeitverlust"] = fehler_counts["Anzahl"].apply(
            lambda x: (
                to_dezimalstunden(timedelta(seconds=x*10))
                if anzeigeformat == "Dezimalstunden"
                else to_hhmmss(timedelta(seconds=x*10))
            )
        )          
      
        if fehler_daten:
            
            total_seconds = fehler_counts["Anzahl"].sum() * 10
            gesamt = pd.DataFrame([{
                "Fehlerbedingung": "Gesamt",
                "Anzahl": fehler_counts["Anzahl"].sum(),
                "Zeitverlust": (
                    to_dezimalstunden(timedelta(seconds=int(total_seconds)))
                    if anzeigeformat == "Dezimalstunden"
                    else to_hhmmss(timedelta(seconds=int(total_seconds)))
                )
            }])
            fehler_counts = pd.concat([fehler_counts, gesamt], ignore_index=True)
            st.dataframe(fehler_counts, use_container_width=True, hide_index=True)

        # Export nach Excel            
            excel_data_3 = convert_df_to_excel(fehler_counts)
            st.download_button(
                label="📥 Zusammenfassung als Excel herunterladen",
                data=excel_data_3,
                file_name="fehler_zusammenfassung.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            
        #else:
            #st.success("✅ Keine fehlerhaften Datenpunkte gefunden.")


   #=== Ausgabe der gruppierten Fehlerzeiträume    
   #===================================================================================== 

        st.markdown("---")
        df_gruppen = pd.DataFrame(gruppen)
        #
        st.markdown("<h3 style='font-size: 24px'>📋 Zusammengefasste Fehlerzeiträume</h3>", unsafe_allow_html=True)
        if not df_gruppen.empty:
                 
            # Summen berechnen
            gesamt_anzahl = df_gruppen["Anzahl"].sum()
            gesamt_dauer = df_gruppen["Dauer_raw"].sum()
            gesamt_dauer_formatiert = (
                to_dezimalstunden(gesamt_dauer)
                if anzeigeformat == "Dezimalstunden"
                else to_hhmmss(gesamt_dauer)
            )
        
            # Summenzeile anfügen
            summenzeile = pd.DataFrame([{
                "Baggerfeld": "Σ",
                "Startzeit": "-",
                "Endzeit": "-",
                "Dauer": gesamt_dauer_formatiert,
                "Anzahl": gesamt_anzahl,
                "Fehlgrund": "-"
            }])
        
            df_anzeige = pd.concat([df_gruppen.drop(columns=["Dauer_raw"]), summenzeile], ignore_index=True)
        
            st.dataframe(df_anzeige, use_container_width=True, hide_index=True)
            
        # Export nach Excel
            excel_data_1 = convert_df_to_excel(df_anzeige)
            st.download_button(
                label="📥 Fehlerzeiträume als Excel herunterladen",
                data=excel_data_1,
                file_name="fehlerzeitraeume.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
       
         
        else:
            st.success("✅ Keine fehlerhaften Datenpunkte gefunden.")
            

        
        
# --- Info anzeigen, falls keine Daten vorhanden sind    
else:
    # Kein Daten-Upload → keine Tabs!
    st.info("Bitte lade mindestens eine MoNa-Datei hoch, um Tabs anzuzeigen.")



