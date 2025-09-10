import xml.etree.ElementTree as ET
from typing import Dict, List, Any

def parse_network(net_file_path: str) -> Dict[str, Any]:
    """
    Parses a SUMO .net.xml file to extract detailed information about edges (roads),
    lanes, and traffic light signal connections for accurate frontend rendering.
    """
    tree = ET.parse(net_file_path)
    root = tree.getroot()
    
    network_data: Dict[str, Any] = {"edges": [], "lanes": [], "tls": {}}

    # Extract edges that are actual roads (not internal junction links)
    for edge in root.findall("edge"):
        if not edge.get("function") == "internal":
            lanes_on_edge = edge.findall("lane")
            if lanes_on_edge:
                shape_str = lanes_on_edge[0].get("shape")
                shape_points = [
                    {"x": float(p.split(',')[0]), "y": float(p.split(',')[1])}
                    for p in shape_str.split(' ') if ',' in p
                ]
                network_data["edges"].append({
                    "id": edge.get("id"),
                    "shape": shape_points,
                    "width": float(lanes_on_edge[0].get("width", 3.2)),
                    "lanes": len(lanes_on_edge)
                })

    # Extract all individual lane shapes for potential detailed drawing
    for lane in root.findall(".//lane"):
        shape_str = lane.get("shape")
        if shape_str:
            shape_points = [
                {"x": float(p.split(',')[0]), "y": float(p.split(',')[1])}
                for p in shape_str.split(' ') if ',' in p
            ]
            network_data["lanes"].append({ "id": lane.get("id"), "shape": shape_points })

    # Extract traffic light connection details
    for tls in root.findall("tlLogic"):
        tls_id = tls.get("id")
        links = []
        for conn in root.findall(f"connection[@tl='{tls_id}']"):
            links.append({
                "from": conn.get("from"),
                "to": conn.get("to"),
                "via": conn.get("via"),
                "linkIndex": int(conn.get("linkIndex"))
            })
        network_data["tls"][tls_id] = {"links": sorted(links, key=lambda x: x['linkIndex'])}

    return network_data