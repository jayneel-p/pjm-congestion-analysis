import json
import os
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

base=Path(os.environ.get('PJM_DECK_BUILD_DIR',Path(__file__).resolve().parents[1]/'build'))
target=base/'output/PJM_GBE_Assessment.pdf'
pdf=canvas.Canvas(str(target),pagesize=(960,540),pageCompression=1)
pdf.setTitle('PJM GBE Data Cleaning, Weather and Trades')
pdf.setAuthor('PJM Flowgate Case Analysis')
pdf.setSubject('Expanded GBE assessment; weather issued 15 October 2026, dated trade values from 14 October')
count=json.loads((base/'private/deck_requirements.json').read_text())['slides']
for i in range(1,count+1):
    png=base/f'private/final_renders/slide-{i:02d}.png'
    assert png.is_file(),png
    pdf.drawImage(ImageReader(str(png)),0,0,width=960,height=540)
    pdf.showPage()
pdf.save()
print(target)
