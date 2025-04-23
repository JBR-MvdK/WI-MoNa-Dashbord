def erkenne_koordinatensystem(df, st=None, sidebar=None):
    rw_max = df["RW_Schiff"].dropna().astype(float).max()
    hw_max = df["HW_Schiff"].dropna().astype(float).max()

    proj_system = None
    epsg_code = None
    auto_erkannt = False

    if rw_max > 30_000_000:
        erkannte_zone = str(int(rw_max))[:2]
        proj_system = "UTM"
        epsg_code = f"EPSG:258{erkannte_zone}"
        auto_erkannt = True

    elif 2_000_000 < rw_max < 5_000_000:
        zone = str(int(rw_max))[0]
        proj_system = "Gauß-Krüger"
        epsg_code = f"EPSG:3146{zone}"
        auto_erkannt = True

    elif 150_000 < rw_max < 300_000 and 300_000 < hw_max < 620_000:
        proj_system = "RD"
        epsg_code = "EPSG:28992"
        auto_erkannt = True

    if st:  # Platzhalter für Status (empty())
        if auto_erkannt:
            st.success(f"Automatisch erkannt: {proj_system} ({epsg_code})")
        else:
            st.warning("Koordinatensystem konnte nicht sicher erkannt werden.")
    if sidebar:  # Sidebar für Widgets
        if not auto_erkannt:
            proj_system = sidebar.selectbox("Bitte Koordinatensystem auswählen", ["UTM", "Gauß-Krüger", "RD (Niederlande)"])
            if proj_system == "UTM":
                utm_zone = sidebar.selectbox("UTM-Zone", ["31", "32", "33", "34"], index=1)
                epsg_code = f"EPSG:258{utm_zone}"
            elif proj_system == "Gauß-Krüger":
                gk_zone = sidebar.selectbox("GK-Zone", ["2", "3", "4", "5"], index=1)
                epsg_code = f"EPSG:3146{gk_zone}"
            elif proj_system == "RD (Niederlande)":
                epsg_code = "EPSG:28992"
    return proj_system, epsg_code, auto_erkannt

