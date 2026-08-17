import pymupdf

doc = pymupdf.open('templates/hillsboro_form.pdf')
page = doc[0]

print("--- Text Blocks in Table ---")
for b in page.get_text('blocks'):
    if 300 <= b[1] <= 600:
        print(f"y0={b[1]:.1f}, y1={b[3]:.1f}, x0={b[0]:.1f}, x1={b[2]:.1f} | Text: {repr(b[4])}")

print("\n--- Horizontal Lines in Table ---")
for d in page.get_drawings():
    r = d['rect']
    if r.height < 5 and 320 <= r.y0 <= 600:
        print(f"y0={r.y0:.1f}, x0={r.x0:.1f}, x1={r.x1:.1f}")
