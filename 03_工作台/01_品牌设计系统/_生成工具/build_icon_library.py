from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "图标"
ROOT.mkdir(parents=True, exist_ok=True)

ICONS = {
    "nav-dashboard": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "nav-pipeline": '<circle cx="12" cy="4" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 6v5M12 11 5 17M12 11l7 6"/>',
    "nav-assets": '<path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 7V5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2"/>',
    "nav-team": '<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 21v-2a6 6 0 0 0-3-5.2"/>',
    "nav-data": '<path d="M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7"/>',
    "home": '<path d="m3 10 9-7 9 7v10H3zM9 21v-6h6v6"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.6 2.6 0 1 1 4.2 2.1c-1 .8-1.7 1.3-1.7 2.9M12 17h.01"/>',
    "document": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 12h6M9 16h6"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.2 2.2 4.7-5"/>',
    "chevron-right": '<path d="m9 5 7 7-7 7"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    "inbox": '<path d="M4 5h16v14H4z"/><path d="m4 14 4 4h8l4-4M9 10h6"/>',
    "layers": '<path d="m12 3 8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="m12 12 8-8"/>',
    "microphone": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/>',
    "flame": '<path d="M12 21c4.4 0 7-3 7-6.6 0-3.2-2.1-5.3-4.1-7.5-.2 2.3-1.3 3.7-2.9 4.7.2-3.2-1.3-5.6-3.7-7.6.3 4-3.3 5.7-3.3 10.1C5 18 8 21 12 21z"/>',
    "lightbulb": '<path d="M9 18h6M10 22h4M8 14.5A7 7 0 1 1 16 14.5c-1 1-1.4 1.8-1.4 3H9.4c0-1.2-.4-2-1.4-3z"/>',
    "puzzle": '<path d="M8 4h3a2 2 0 1 1 4 0h3v5a2 2 0 1 0 0 4v5h-5a2 2 0 1 1-4 0H4v-5a2 2 0 1 0 0-4V4z"/>',
    "play": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/>',
    "structure": '<rect x="4" y="4" width="5" height="5" rx="1"/><rect x="15" y="4" width="5" height="5" rx="1"/><rect x="4" y="15" width="5" height="5" rx="1"/><path d="M12 6h3M6 9v6M9 17h6"/>',
    "pencil": '<path d="m4 20 4.2-1 10-10a2.5 2.5 0 0 0-3.5-3.5l-10 10z"/><path d="m13 6 5 5M4 20l.8-4.8"/>',
    "audit": '<path d="M12 3 20 7v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7z"/><path d="m8.5 12 2.2 2.2 4.7-5"/>',
    "output": '<path d="M5 7h14v13H5z"/><path d="M8 7V4h8v3M8 12h8M8 16h5"/>',
    "gallery": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4 17 5-5 3 3 2-2 6 4"/>',
    "folder": '<path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "chat": '<path d="M5 5h14v11H9l-4 4z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>',
    "book": '<path d="M4 4.5A3.5 3.5 0 0 1 7.5 1H12v19H7.5A3.5 3.5 0 0 0 4 23zM20 4.5A3.5 3.5 0 0 0 16.5 1H12v19h4.5A3.5 3.5 0 0 1 20 23z"/>',
    "spark": '<path d="m12 2 1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5zM19 17l.7 2.3L22 20l-2.3.7L19 23l-.7-2.3L16 20l2.3-.7z"/>',
    "chart-pie": '<path d="M11 3a9 9 0 1 0 10 10h-10z"/><path d="M13 3v8h8A8 8 0 0 0 13 3z"/>'
}

TEMPLATE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{}</svg>\n'

for name, body in ICONS.items():
    (ROOT / f"{name}.svg").write_text(TEMPLATE.format(body), encoding="utf-8")

(ROOT / "manifest.json").write_text(
    '{\n  "grid": 24,\n  "strokeWidth": 1.7,\n  "icons": [' + ', '.join(f'"{name}"' for name in ICONS) + ']\n}\n',
    encoding="utf-8",
)
