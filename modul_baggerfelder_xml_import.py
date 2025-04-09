import xml.etree.ElementTree as ET
from shapely.geometry import Polygon
from pyproj import Transformer

def parse_baggerfelder(xml_path, epsg_code_from_mona):
    """
    Liest Baggerfelder aus einer LandXML-Datei ein und wandelt sie in WGS84 um.

    Args:
        xml_path (str): Pfad zur XML-Datei
        epsg_code_from_mona (str): EPSG-Code, z. B. 'EPSG:25832'

    Returns:
        List[Dict]: Liste von Dicts mit Polygon, Name und Solltiefe
    """
    transformer = Transformer.from_crs(epsg_code_from_mona, "EPSG:4326", always_xy=True)

    ns = {'ns': 'http://www.landxml.org/schema/LandXML-1.2'}
    tree = ET.parse(xml_path)
    root = tree.getroot()

    polygons = []

    for plan_feature in root.findall(".//ns:PlanFeature", ns):
        name = plan_feature.attrib.get("name", "Unbenannt")
        coord_geom = plan_feature.find("ns:CoordGeom", ns)
        if coord_geom is None:
            continue

        points = []
        tiefen = []

        for line in coord_geom.findall("ns:Line", ns):
            start = line.find("ns:Start", ns)
            end = line.find("ns:End", ns)
            if start is not None and end is not None:
                start_vals = list(map(float, start.text.strip().split()))
                end_vals = list(map(float, end.text.strip().split()))

                # Koordinaten zuweisen: HW = Y, RW = X
                hw_raw = start_vals[0]
                rw_raw = start_vals[1]

                # Normalisierung wie bei MoNa (z. B. UTM mit Zonenkennung)
                if epsg_code_from_mona.startswith("EPSG:258") and rw_raw > 30_000_000:
                    rw_raw -= int(epsg_code_from_mona[-2:]) * 1_000_000

                points.append((rw_raw, hw_raw))  # (RW, HW) = (X, Y)
                tiefen.append(start_vals[2])

        if points and points[0] != points[-1]:
            points.append(points[0])  # Polygon schließen

        # Transformation in WGS84
        transformed = [transformer.transform(x, y) for x, y in points]

        solltiefe = round(sum(tiefen) / len(tiefen), 2) if tiefen else None

        polygons.append({
            "name": name,
            "polygon": Polygon(transformed),
            "solltiefe": solltiefe
        })

    return polygons
