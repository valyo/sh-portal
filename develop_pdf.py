import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from weasyprint import HTML
from jinja2 import Template
from datetime import datetime

# --- CONFIGURATION ---
INPUT_HTML = "sh_portal/templates/certificate_pdf_template.html"
OUTPUT_PDF = "certificate_preview.pdf"

# --- DUMMY DATA ---
# This dictionary matches the variables in your HTML template
MOCK_DATA = {
    "booking": {
        "id": 5,
        "name": "Kristina Holmberg",
        "certificate_name": "KRISTINA HOLMBERG",
        "quantity": 2
    },
    "season": {
        "year": "2025"
    },
    "current_date": datetime.now().strftime("%Y-%m-%d")
}

def generate_pdf():
    print(f"[{time.strftime('%H:%M:%S')}] Regenerating PDF with dummy data...")
    try:
        # 1. Read the template file
        with open(INPUT_HTML, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 2. Render the template with Jinja2
        template = Template(template_content)
        rendered_html = template.render(**MOCK_DATA)
        
        # 3. Convert to PDF with WeasyPrint
        # base_url='sh_portal' ensures it can find images like 'static/honey_1.png'
        HTML(string=rendered_html, base_url='sh_portal').write_pdf(OUTPUT_PDF)
        
        print("✔ Success! Preview updated.")
    except Exception as e:
        print(f"✘ Error: {e}")

class ReloadHandler(FileSystemEventHandler):
    def on_modified(self, event):
        # Only trigger if the HTML template itself changes
        if os.path.abspath(event.src_path) == os.path.abspath(INPUT_HTML):
            generate_pdf()

if __name__ == "__main__":
    generate_pdf()
    
    observer = Observer()
    observer.schedule(ReloadHandler(), path='.', recursive=True)
    observer.start()
    print(f"Watching project root recursively for changes in {INPUT_HTML}... (Ctrl+C to stop)")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()