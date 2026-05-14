ASSETS = [
    # --- DAX INDEX + ETF (priorita') ---
    {"ticker": "^GDAXI",    "name": "DAX 40 Index",             "category": "DAX",       "short_enabled": True},
    {"ticker": "EWG",       "name": "iShares MSCI Germany ETF", "category": "DAX",       "short_enabled": True},

    # --- DAX BLUE CHIP ---
    {"ticker": "SIE.DE",    "name": "Siemens AG",               "category": "DAX",       "short_enabled": True},
    {"ticker": "ALV.DE",    "name": "Allianz SE",               "category": "DAX",       "short_enabled": True},
    {"ticker": "BMW.DE",    "name": "BMW Group",                "category": "DAX",       "short_enabled": True},
    {"ticker": "DTE.DE",    "name": "Deutsche Telekom",         "category": "DAX",       "short_enabled": True},

    # --- ORO & METALLI ---
    {"ticker": "GLD",       "name": "SPDR Gold Shares",         "category": "Commodity", "short_enabled": True},
    {"ticker": "GC=F",      "name": "Oro (Futures)",            "category": "Commodity", "short_enabled": True},
    {"ticker": "GDX",       "name": "VanEck Gold Miners ETF",   "category": "Commodity"},
    {"ticker": "SLV",       "name": "iShares Silver Trust",     "category": "Commodity"},
    {"ticker": "USO",       "name": "US Oil Fund (Petrolio)",   "category": "Commodity"},

    # --- ETF GLOBALI (non-USA) ---
    {"ticker": "VWCE.DE",   "name": "Vanguard FTSE All-World",  "category": "ETF"},
    {"ticker": "IWDA.AS",   "name": "iShares Core MSCI World",  "category": "ETF"},
    {"ticker": "EEM",       "name": "iShares MSCI Emerg. Mkt",  "category": "ETF"},

    # --- AZIONI EUROPEE ---
    {"ticker": "ASML.AS",   "name": "ASML Holding",             "category": "Azione EU"},
    {"ticker": "SAP.DE",    "name": "SAP SE",                   "category": "Azione EU"},
    {"ticker": "MC.PA",     "name": "LVMH",                     "category": "Azione EU"},
    {"ticker": "AIR.PA",    "name": "Airbus",                   "category": "Azione EU"},
    {"ticker": "TTE.PA",    "name": "TotalEnergies",            "category": "Azione EU"},
    {"ticker": "SHEL.L",    "name": "Shell",                    "category": "Azione EU"},
    {"ticker": "HSBA.L",    "name": "HSBC",                     "category": "Azione EU"},
    {"ticker": "NESN.SW",   "name": "Nestle",                   "category": "Azione EU"},
    {"ticker": "ROG.SW",    "name": "Roche Holding",            "category": "Azione EU"},
    {"ticker": "NOVO-B.CO", "name": "Novo Nordisk",             "category": "Azione EU"},

    # --- AZIONI ITALIANE ---
    {"ticker": "ENI.MI",    "name": "ENI",                      "category": "Azione IT"},
    {"ticker": "ENEL.MI",   "name": "ENEL",                     "category": "Azione IT"},
    {"ticker": "ISP.MI",    "name": "Intesa Sanpaolo",          "category": "Azione IT"},
    {"ticker": "UCG.MI",    "name": "UniCredit",                "category": "Azione IT"},
]
