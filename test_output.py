from pathlib import Path                                                         
from starter.edinburgh_research.integrity import extract_testid_facts
import json

flyer = Path('/Users/dgwalters/Library/Application Support/sovereign-agent/examples/ex5-edinburgh-research/sess_2f5bd9478e9b/workspace/flyer.html').read_text()
 
print(json.dumps(extract_testid_facts(flyer), indent=2))            
