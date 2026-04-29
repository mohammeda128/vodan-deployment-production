import json
import urllib.parse
import requests
import os
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, SKOS, XSD, RDFS

# --- 1. RDF Generation Logic ---
ontology_file = "hds_cdm.ttl"
g = Graph()

try:
    if os.path.exists(ontology_file):
        g.parse(ontology_file, format="turtle")
        print(f"Loaded ontology from {ontology_file}")
except Exception as e:
    print(f"Error loading ontology: {e}")

HDS = Namespace("http://example.org/hds#")
g.bind("hds", HDS)

data_file = "cleaned_data.json"
try:
    with open(data_file, "r") as f:
        victims_data = json.load(f)
    print(f"Loaded data from {data_file}")
except FileNotFoundError:
    print(f"Error: {data_file} not found. Using empty list.")
    victims_data = []

def sanitize_uri(value):
    if not value: return "Unknown"
    return urllib.parse.quote(str(value).replace(" ", "_"))

def safe_add(graph, subject, predicate, obj):
    if subject and predicate and obj is not None:
        graph.add((subject, predicate, obj))

def as_literal(value, datatype=XSD.string):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, list):
        if not value: return None
        value = ", ".join([str(v) for v in value])
    
    if datatype == XSD.integer:
        try:
            return Literal(int(value), datatype=datatype)
        except (ValueError, TypeError):
            return None
    return Literal(value, datatype=datatype)

# Process victims
for victim in victims_data:
    victim_id = victim.get("victim_id", "Unknown")
    victim_uri = URIRef(f"http://example.org/resource/Victim/{sanitize_uri(victim_id)}")
    safe_add(g, victim_uri, RDF.type, HDS.Victim)
    safe_add(g, victim_uri, HDS.id, as_literal(victim_id))
    safe_add(g, victim_uri, HDS.age, as_literal(victim.get("age"), XSD.integer))
    
    # Traffickers & Incidents
    for trafficker_name in victim.get("trafficker_name", []):
        t_uri = URIRef(f"http://example.org/resource/Trafficker/{sanitize_uri(trafficker_name)}")
        safe_add(g, t_uri, RDF.type, HDS.Trafficker)
        
        incident_uri = URIRef(f"http://example.org/resource/Incident/T_{sanitize_uri(victim_id)}_{sanitize_uri(trafficker_name)}")
        safe_add(g, incident_uri, RDF.type, HDS.Incident)
        safe_add(g, incident_uri, HDS.affected, victim_uri)
        safe_add(g, incident_uri, HDS.involved, t_uri)

# Save local copy
output_file = "Human_trafficking_output.ttl"
g.serialize(destination=output_file, format="turtle")

# --- 2. Cloud AllegroGraph Push Logic ---

# Clean host and ensure https
host = os.getenv("AGRAPH_HOST", "https://ag1jdz6nqkhfjj72.allegrograph.cloud/").strip("/")
if not host.startswith("http"):
    host = f"https://{host}"

repo_name = os.getenv("AGRAPH_REPOSITORY", "DT01")
username = os.getenv("AGRAPH_USER", "admin")
password = os.getenv("AGRAPH_PASSWORD", "KbA8KuX3E7aZSOVwGCxiK4")

# Use a session for auth
session = requests.Session()
session.auth = (username, password)

# Base URL for the root catalog
base_url = f"{host}/repositories/{repo_name}"

try:
    print(f"Targeting: {base_url}")
    
    # 1. Check/Create Repository
    check_response = session.get(base_url)
    
    if check_response.status_code == 404:
        print(f"Creating repository {repo_name}...")
        # To create in the root catalog, we PUT to the repo URL
        create_resp = session.put(base_url)
        create_resp.raise_for_status()
        print("Repository created successfully.")
    
    # 2. Get Initial Size
    size_resp = session.get(f"{base_url}/size")
    initial_count = int(size_resp.text.strip()) if size_resp.ok else 0
    
    # 3. Upload Data
    print("Uploading RDF data...")
    with open(output_file, "rb") as f:
        upload_resp = session.post(
            f"{base_url}/statements",
            headers={"Content-Type": "text/turtle"},
            data=f
        )
    
    if upload_resp.status_code in [200, 201, 204]:
        # 4. Verify
        final_size_resp = session.get(f"{base_url}/size")
        final_count = int(final_size_resp.text.strip())
        print(f"Upload Complete! Triples added: {final_count - initial_count}")
        print(f"Total triples now: {final_count}")
    else:
        print(f"Upload failed: {upload_resp.status_code} - {upload_resp.text}")

except Exception as e:
    print(f"An error occurred: {e}")