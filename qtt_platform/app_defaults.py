"""
Built-in defaults for the QTT OS app (pure data, no frappe) — seeded by
qtt_platform.app_setup on install/migrate.
"""

#: Built-in themes. QTT Midnight is the brand default (queentouchtech
#: website palette); the rest give users with different needs and tastes
#: real choice — incl. colour-blind-safe and high-contrast options.
DEFAULT_THEMES = [
	{
		"theme_key": "qtt-midnight",
		"label": "QTT Midnight",
		"sort_order": 1,
		"light": dict(primary="#3858F8", secondary="#5B6CF0", background="#F6F7FB", surface="#FFFFFF", surface_variant="#EEF1F9",
					  text="#0E1220", text_muted="#5B6375", border="#DCE0EC", error="#D92D3A", success="#16A34A", warning="#D97706"),
		"dark": dict(primary="#3858F8", secondary="#8B9CFF", background="#080810", surface="#11131C", surface_variant="#1A1D2B",
					 text="#F8F8F8", text_muted="#8890A2", border="#262A3A", error="#F2555A", success="#22C55E", warning="#F5A524"),
	},
	{
		"theme_key": "ocean",
		"label": "Ocean",
		"sort_order": 2,
		"light": dict(primary="#0B7A8F", secondary="#2F6FD6", background="#F4F9FA", surface="#FFFFFF", surface_variant="#E6F2F4",
					  text="#0B1F24", text_muted="#4D6A70", border="#CFE2E6", error="#C8323E", success="#15803D", warning="#B45309"),
		"dark": dict(primary="#2BC2D6", secondary="#6EA8FF", background="#061417", surface="#0D1F23", surface_variant="#14292E",
					 text="#E9F6F8", text_muted="#8FB0B6", border="#1F3A40", error="#F06A73", success="#34D399", warning="#FBBF24"),
	},
	{
		"theme_key": "forest",
		"label": "Forest",
		"sort_order": 3,
		"light": dict(primary="#2E7D4F", secondary="#6B8E23", background="#F5F8F4", surface="#FFFFFF", surface_variant="#E8F1E9",
					  text="#132017", text_muted="#55695B", border="#D3E2D6", error="#C2343F", success="#15803D", warning="#B45309"),
		"dark": dict(primary="#4CC27E", secondary="#A3C95A", background="#08120C", surface="#0F1C14", surface_variant="#17271D",
					 text="#EAF5EE", text_muted="#93AE9B", border="#22382A", error="#F06A73", success="#4ADE80", warning="#FBBF24"),
	},
	{
		"theme_key": "sunset",
		"label": "Sunset",
		"sort_order": 4,
		"components": {"card_style": "elevated", "input_style": "filled", "button_shape": "pill"},
		"light": dict(primary="#D9480F", secondary="#C2255C", background="#FFF8F3", surface="#FFFFFF", surface_variant="#FCEDE3",
					  text="#25140B", text_muted="#6F5446", border="#F0D9CC", error="#B91C1C", success="#15803D", warning="#B45309"),
		"dark": dict(primary="#FF8A4C", secondary="#F06595", background="#140A06", surface="#1F120C", surface_variant="#2A1A12",
					 text="#FCEFE7", text_muted="#BC9C8C", border="#3B271C", error="#F87171", success="#4ADE80", warning="#FBBF24"),
	},
	{
		"theme_key": "royal",
		"label": "Royal",
		"sort_order": 5,
		"light": dict(primary="#4B2E83", secondary="#C48A12", background="#F8F6FC", surface="#FFFFFF", surface_variant="#EFEAF8",
					  text="#1A1229", text_muted="#5F5571", border="#DFD7EE", error="#C2343F", success="#15803D", warning="#B45309"),
		"dark": dict(primary="#9C7BE0", secondary="#E8B02E", background="#0E0915", surface="#171021", surface_variant="#21182E",
					 text="#F3EEFB", text_muted="#A698BD", border="#2F2440", error="#F06A73", success="#4ADE80", warning="#FBBF24"),
	},
	{
		"theme_key": "rose",
		"label": "Rose",
		"sort_order": 6,
		"components": {"card_style": "elevated", "input_style": "filled", "button_shape": "pill"},
		"light": dict(primary="#C2255C", secondary="#7048E8", background="#FFF6F9", surface="#FFFFFF", surface_variant="#FBE9EF",
					  text="#2A0F19", text_muted="#74515D", border="#F1D5DF", error="#B91C1C", success="#15803D", warning="#B45309"),
		"dark": dict(primary="#F06595", secondary="#B197FC", background="#14080D", surface="#1F0F15", surface_variant="#2B161E",
					 text="#FCEEF3", text_muted="#BF97A5", border="#3D2029", error="#F87171", success="#4ADE80", warning="#FBBF24"),
	},
	{
		"theme_key": "graphite",
		"label": "Graphite",
		"sort_order": 7,
		"components": {"card_style": "flat", "input_style": "outlined", "button_shape": "rounded"},
		"light": dict(primary="#334155", secondary="#0F766E", background="#F6F7F8", surface="#FFFFFF", surface_variant="#ECEEF1",
					  text="#111418", text_muted="#5B6470", border="#DADDE2", error="#C2343F", success="#15803D", warning="#B45309"),
		"dark": dict(primary="#CBD5E1", secondary="#5EEAD4", background="#0B0C0E", surface="#141619", surface_variant="#1C1F23",
					 text="#F1F3F5", text_muted="#959DA8", border="#2A2E34", error="#F06A73", success="#4ADE80", warning="#FBBF24"),
	},
	{
		# Okabe–Ito palette: distinguishable for the common forms of
		# colour-vision deficiency (no red/green-only signals).
		"theme_key": "clear-vision",
		"label": "Clear Vision (colour-blind friendly)",
		"sort_order": 8,
		"light": dict(primary="#0072B2", secondary="#E69F00", background="#F7F8FA", surface="#FFFFFF", surface_variant="#ECF0F4",
					  text="#101418", text_muted="#4F5A66", border="#D5DCE3", error="#D55E00", success="#009E73", warning="#E69F00"),
		"dark": dict(primary="#56B4E9", secondary="#E69F00", background="#0A0D10", surface="#12171C", surface_variant="#1A2027",
					 text="#F2F5F8", text_muted="#9AA6B2", border="#28313A", error="#FF8C42", success="#2BD9A8", warning="#F0E442"),
	},
	{
		# Maximum contrast (WCAG AAA text), for low vision and bright sunlight.
		"theme_key": "high-contrast",
		"label": "High Contrast",
		"sort_order": 9,
		"radius": 6,
		# Clear edges on every control for low vision.
		"components": {"card_style": "outlined", "input_style": "outlined", "button_shape": "rounded"},
		"light": dict(primary="#0033CC", secondary="#6B00B3", background="#FFFFFF", surface="#FFFFFF", surface_variant="#F0F0F0",
					  text="#000000", text_muted="#1F1F1F", border="#000000", error="#B00000", success="#006100", warning="#7A4A00"),
		"dark": dict(primary="#FFD500", secondary="#7FDBFF", background="#000000", surface="#000000", surface_variant="#141414",
					 text="#FFFFFF", text_muted="#E6E6E6", border="#FFFFFF", error="#FF6B6B", success="#5CFF7A", warning="#FFD500"),
	},
]
