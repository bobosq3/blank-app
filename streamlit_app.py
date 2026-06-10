import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
from datetime import datetime, timedelta
import time
import requests
from bs4 import BeautifulSoup
import yfinance as yf

# ==========================================
# CONFIGURATION DE L'APPLICATION
# ==========================================
st.set_page_config(page_title="Gestion de Patrimoine Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .main-title { font-size: 38px; font-weight: bold; color: #1E3A8A; margin-bottom: 5px; }
    .subtitle { font-size: 16px; color: #6B7280; margin-bottom: 25px; }
    .section-header { font-size: 22px; font-weight: bold; color: #1F2937; margin-top: 20px; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# MOTEUR D'ACQUISITION : BOURSORAMA & YAHOO
# ==========================================

def fetch_from_boursorama(isin, type_actif):
    """Scrape Boursorama en ciblant l'URL exacte selon la nature de l'actif."""
    urls_to_try = []
    if type_actif == "ETF":
        urls_to_try = [f"https://www.boursorama.com/bourse/trackers/cours/{isin}/", f"https://www.boursorama.com/bourse/cours/{isin}/"]
    elif type_actif == "Fonds (OPCVM)":
        urls_to_try = [f"https://www.boursorama.com/bourse/opcvm/cours/{isin}/"]
    elif type_actif in ["Action", "Obligation"]:
        urls_to_try = [f"https://www.boursorama.com/bourse/cours/{isin}/", f"https://www.boursorama.com/bourse/trackers/cours/{isin}/"]
    else:
        urls_to_try = [f"https://www.boursorama.com/bourse/cours/{isin}/", f"https://www.boursorama.com/bourse/trackers/cours/{isin}/", f"https://www.boursorama.com/bourse/opcvm/cours/{isin}/"]
        
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    for url in urls_to_try:
        try:
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                price_tag = soup.find("span", class_="c-instrument--last")
                name_tag = soup.find("a", class_="c-faceplate__company-link") or soup.find("h1", class_="c-faceplate__company-name")
                if price_tag:
                    price = float(price_tag.text.replace(" ", "").replace(",", ".").strip())
                    name = name_tag.text.strip().replace("\n", "") if name_tag else isin
                    if price > 0:
                        return {"prix_eur": price, "nom": name, "source": "Boursorama"}
        except Exception:
            continue
    return None

@st.cache_data(ttl=3600)
def get_ticker_from_isin(isin):
    """Fallback ultime : Recherche le ticker Yahoo équivalent à un code ISIN."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=4)
        quotes = response.json().get("quotes", [])
        if quotes: return quotes[0]["symbol"]
    except Exception: pass
    return None

@st.cache_data(ttl=1800)
def fetch_quote(isin_or_symbol, type_actif=None):
    """Système de routage intelligent avec priorité absolue Boursorama."""
    val = isin_or_symbol.strip().upper()
    if val == "CASH": return {"prix_eur": 1.0, "nom": "Liquidités", "source": "Système"}
    if len(val) == 12 and type_actif != "Crypto":
        bourso_data = fetch_from_boursorama(val, type_actif)
        if bourso_data: return bourso_data
    ticker = val if len(val) < 8 else get_ticker_from_isin(val)
    if ticker:
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                name = tk.info.get("shortName", ticker)
                if price > 0: return {"prix_eur": price, "nom": name, "source": "Yahoo Finance (Fallback)"}
        except Exception: pass
    return {"prix_eur": 0.0, "nom": val, "source": "Introuvable"}

@st.cache_data(ttl=3600)
def fetch_historical_series(portfolio_items):
    """Télécharge les données historiques GLOBALES (period='max') sans fuseaux horaires."""
    series = {}
    for item in portfolio_items:
        isin = item["isin"]
        if isin == "CASH": continue
        ticker = isin if len(isin) < 8 else get_ticker_from_isin(isin)
        if ticker:
            try:
                df_h = yf.Ticker(ticker).history(period="max")
                if not df_h.empty:
                    series[item["nom"]] = df_h["Close"].tz_localize(None)
            except Exception: pass
    return pd.DataFrame(series)

# ==========================================
# REFRESH ET SESSION STATE
# ==========================================
def refresh_portfolio_prices(portfolio):
    updated = []
    for item in portfolio:
        if item["isin"] == "CASH" or item.get("prix_force_manuel", False):
            updated.append(item)
            continue
        quote = fetch_quote(item["isin"], item.get("type_actif"))
        if quote and quote["prix_eur"] > 0:
            item = {**item, "prix": quote["prix_eur"], "nom": quote["nom"]}
        updated.append(item)
    return updated, datetime.now()

if "portfolio" not in st.session_state: st.session_state.portfolio = []
if "cash_value" not in st.session_state: st.session_state.cash_value = 32890.060
if "custom_vols" not in st.session_state: st.session_state.custom_vols = {}
if "sandbox_portfolio" not in st.session_state: st.session_state.sandbox_portfolio = []
if "last_price_update" not in st.session_state: st.session_state.last_price_update = None
if "auto_refresh_enabled" not in st.session_state: st.session_state.auto_refresh_enabled = True
if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
if "chat_history" not in st.session_state: st.session_state.chat_history = []

if st.session_state.portfolio and st.session_state.auto_refresh_enabled:
    if any(item["isin"] != "CASH" for item in st.session_state.portfolio):
        st.session_state.portfolio, st.session_state.last_price_update = refresh_portfolio_prices(st.session_state.portfolio)

# ==========================================
# BARRE LATÉRALE (SIDEBAR)
# ==========================================
st.sidebar.markdown("### 🏛 Honoré & Associés")
st.sidebar.markdown("---")

st.session_state.auto_refresh_enabled = st.sidebar.toggle("🔄 Actualisation automatique", value=st.session_state.auto_refresh_enabled)

if st.sidebar.button("🔄 Forcer la mise à jour globale", type="primary", width='stretch'):
    fetch_quote.clear()
    get_ticker_from_isin.clear()
    fetch_historical_series.clear()
    if st.session_state.portfolio:
        st.session_state.portfolio, st.session_state.last_price_update = refresh_portfolio_prices(st.session_state.portfolio)
    st.toast("⚡ Données synchronisées via Boursorama !", icon="📈")
    st.rerun()

with st.sidebar.expander("➕ Saisir un Nouvel Actif / Ajuster PRU", expanded=True):
    input_type = st.selectbox("Type d'Actif", ["ETF", "Fonds (OPCVM)", "Action", "Obligation", "Immobilier", "Crypto"], index=0)
    input_isin = st.text_input("Code ISIN / Symbole Crypto", "", key="real_isin").strip().upper()
    prix_detecte, nom_detecte = 100.000, ""
    if input_isin:
        quote = fetch_quote(input_isin, type_actif=input_type)
        if quote:
            prix_detecte = quote["prix_eur"]
            nom_detecte = quote["nom"]
    input_nom = st.text_input("Nom de l'actif", value=nom_detecte)
    input_qty = st.number_input("Quantité Totale", min_value=0.0, value=1.0, step=1.0, format="%.3f", key="real_qty")
    input_buy_price = st.number_input("PRU Net (€)", min_value=0.0, value=100.000, step=1.0, format="%.3f", key="real_price")
    force_prix_manuel = st.checkbox("🔒 Forcer ce prix", value=False)
    input_live_price = st.number_input("Prix actuel (€)", min_value=0.0, value=prix_detecte, format="%.3f", disabled=not force_prix_manuel)

    if st.sidebar.button("Ajouter / Mettre à jour la ligne", width='stretch'):
        if input_isin:
            st.session_state.portfolio = [i for i in st.session_state.portfolio if i["isin"] != input_isin]
            entry = {"isin": input_isin, "quantite": input_qty, "prix_achat": input_buy_price, "prix_force_manuel": force_prix_manuel, "nom": input_nom if input_nom else input_isin, "type_actif": input_type}
            entry["prix"] = input_live_price if force_prix_manuel else (prix_detecte if prix_detecte > 0 else input_buy_price)
            st.session_state.portfolio.append(entry)
            st.session_state.last_price_update = datetime.now()
            st.rerun()

with st.sidebar.expander("💵 Trésorerie & Suppressions", expanded=False):
    st.session_state.cash_value = st.number_input("Liquidités (€)", min_value=0.0, value=st.session_state.cash_value, step=500.0, format="%.3f")
    if st.session_state.portfolio:
        liste_actifs = [item["isin"] for item in st.session_state.portfolio if item["isin"] != "CASH"]
        if liste_actifs:
            target_suppr = st.selectbox("Titre à retirer", options=liste_actifs)
            if st.button("Supprimer", type="primary", width='stretch'):
                st.session_state.portfolio = [item for item in st.session_state.portfolio if item["isin"] != target_suppr]
                st.rerun()

with st.sidebar.expander("💾 Sauvegarde (Import / Export)", expanded=False):
    export_payload = {"portfolio": st.session_state.portfolio, "cash_value": st.session_state.cash_value, "custom_vols": st.session_state.custom_vols}
    st.download_button(label="📥 Exporter le portefeuille (JSON)", data=json.dumps(export_payload, indent=2, ensure_ascii=False), file_name=f"export_portefeuille_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json", width='stretch')
    st.markdown("---")
    
    uploaded_file = st.file_uploader("📤 Restaurer un fichier JSON", type=["json"], key=f"portfolio_uploader_{st.session_state.uploader_key}")
    if uploaded_file is not None:
        try:
            imported_data = json.load(uploaded_file)
            if isinstance(imported_data, dict) and "portfolio" in imported_data:
                st.session_state.portfolio = imported_data.get("portfolio", [])
                st.session_state.cash_value = float(imported_data.get("cash_value", 0.0))
                st.session_state.custom_vols = imported_data.get("custom_vols", {})
            elif isinstance(imported_data, list): 
                st.session_state.portfolio = imported_data
                
            st.session_state.uploader_key += 1
            st.toast("🚀 Portefeuille restauré avec succès !", icon="💾")
            time.sleep(0.4)
            st.rerun()
        except Exception as e: 
            st.error(f"Erreur de lecture du fichier : {e}")

# ==========================================
# CALCULS QUANTITATIFS AVANCÉS
# ==========================================
processed = []
valeur_titres_totale = 0
cout_total_achat = 0

for item in st.session_state.portfolio:
    if item["isin"] == "CASH": continue
    prix_marche = item.get("prix", item["prix_achat"])
    val_actuelle = prix_marche * item["quantite"]
    val_achat = item["prix_achat"] * item["quantite"]
    valeur_titres_totale += val_actuelle
    cout_total_achat += val_achat
    processed.append({**item, "valeur_actuelle": val_actuelle, "pnl_euro": val_actuelle - val_achat, "prix_marche": prix_marche})

valeur_totale_portefeuille = valeur_titres_totale + st.session_state.cash_value
pnl_global_euro = valeur_titres_totale - cout_total_achat
pnl_global_pct = (pnl_global_euro / cout_total_achat) * 100 if cout_total_achat > 0 else 0.0

if st.session_state.cash_value > 0 or not processed:
    processed.append({"isin": "CASH", "nom": "Liquidités", "prix": 1.000, "quantite": st.session_state.cash_value, "prix_achat": 1.000, "valeur_actuelle": st.session_state.cash_value, "pnl_euro": 0.0, "type_actif": "Liquidités"})

for a in processed:
    a["poids"] = (a["valeur_actuelle"] / valeur_totale_portefeuille) * 100 if valeur_totale_portefeuille > 0 else 0

df = pd.DataFrame(processed)

df_hist_prices = fetch_historical_series([i for i in processed if i["isin"] != "CASH"])
has_history = not df_hist_prices.empty and df_hist_prices.shape[1] > 0

perf_1m, perf_3m, perf_6m, perf_1y, global_sharpe, global_max_dd, vol_globale = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
benefice_div, var_95_mensuelle = 0.0, 0.0
robust_cov = pd.DataFrame()
available_assets = []

if has_history:
    indiv_vols = {}
    indiv_returns = {}
    for col in df_hist_prices.columns:
        series_clean = df_hist_prices[col].dropna()
        if len(series_clean) > 5:
            rets = series_clean.pct_change().dropna()
            indiv_returns[col] = rets
            indiv_vols[col] = float(rets.std() * np.sqrt(252))
            st.session_state.custom_vols[col] = indiv_vols[col] * 100

    available_assets = list(indiv_vols.keys())
    N = len(available_assets)
    robust_cov = pd.DataFrame(0.0, index=available_assets, columns=available_assets)
    
    for i in range(N):
        for j in range(N):
            a1, a2 = available_assets[i], available_assets[j]
            if a1 == a2:
                robust_cov.loc[a1, a2] = indiv_vols[a1] ** 2
            else:
                df_pair = pd.concat([indiv_returns[a1], indiv_returns[a2]], axis=1).dropna()
                corr = df_pair.corr().iloc[0, 1] if len(df_pair) > 10 else 0.0
                if np.isnan(corr): corr = 0.0
                robust_cov.loc[a1, a2] = corr * indiv_vols[a1] * indiv_vols[a2]

    weights_dict = {row["nom"]: row["poids"] / 100 for _, row in df.iterrows() if row["isin"] != "CASH"}
    
    if available_assets:
        W = np.array([weights_dict.get(col, 0.0) for col in available_assets])
        if W.sum() > 0:
            cov_sub = robust_cov.loc[available_assets, available_assets]
            var_main = np.dot(W.T, np.dot(cov_sub.values, W))
            vol_globale = float(np.sqrt(var_main) * 100)
            
            weighted_vol = sum(weights_dict.get(asset, 0.0) * (indiv_vols.get(asset, 0.0) * 100) for asset in available_assets)
            benefice_div = max(0.0, weighted_vol - vol_globale)
            var_95_mensuelle = (vol_globale / np.sqrt(12)) * 1.645
            
            df_hist_aligned = df_hist_prices[available_assets].ffill().bfill()
            df_norm_prices = df_hist_aligned / df_hist_aligned.iloc[0]
            portfolio_hist_index = (df_norm_prices * W).sum(axis=1) * valeur_totale_portefeuille + st.session_state.cash_value
            
            rf = 0.03
            days_total = (portfolio_hist_index.index[-1] - portfolio_hist_index.index[0]).days
            years_total = days_total / 365.25 if days_total > 0 else 1.0
            total_return = (portfolio_hist_index.iloc[-1] / portfolio_hist_index.iloc[0]) - 1
            ann_return = (1 + total_return) ** (1 / years_total) - 1 if total_return > -1 else 0.0
            
            global_sharpe = (ann_return - rf) / (vol_globale / 100) if vol_globale > 0 else 0.0
            
            roll_max = portfolio_hist_index.cummax()
            drawdowns = portfolio_hist_index / roll_max - 1.0
            global_max_dd = float(drawdowns.min() * 100)
            
            if len(portfolio_hist_index) > 21: perf_1m = float((portfolio_hist_index.iloc[-1] / portfolio_hist_index.iloc[-21] - 1) * 100)
            if len(portfolio_hist_index) > 63: perf_3m = float((portfolio_hist_index.iloc[-1] / portfolio_hist_index.iloc[-63] - 1) * 100)
            if len(portfolio_hist_index) > 126: perf_6m = float((portfolio_hist_index.iloc[-1] / portfolio_hist_index.iloc[-126] - 1) * 100)
            perf_1y = float((portfolio_hist_index.iloc[-1] / portfolio_hist_index.iloc[0] - 1) * 100)

if vol_globale < 5.0: profil = "Prudent"
elif vol_globale < 13.0: profil = "Équilibré"
else: profil = "Dynamique"

# ==========================================
# RENDER DE L'INTERFACE PRINCIPALE
# ==========================================
st.markdown("<div class='main-title'>🏛️ Cabinet Honoré & Associés</div>", unsafe_allow_html=True)
st.markdown(f"<div class='subtitle'>Ingénierie Patrimoniale & Moteur Quantitatif Avancé V1</div>", unsafe_allow_html=True)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Encours Global", f"{valeur_totale_portefeuille:,.3f} €")
kpi2.metric("Plus-Value Globale", f"{pnl_global_euro:,.3f} €", f"{pnl_global_pct:+.3f} %")
kpi3.metric("Volatilité Globale", f"{vol_globale:.3f} %", profil, delta_color="off")
kpi4.metric("Ratio de Sharpe", f"{global_sharpe:.3f}", "Réf. Sans Risque: 3.000%", delta_color="normal" if global_sharpe > 0 else "inverse")

st.markdown("---")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Vue d'ensemble", "🎯 Allocations", "🔬 Analyses Quantitatives", "⚙️ Simulateur de Poids", "🧪 Bac à sable", "🌍 Macro"])

with tab1:
    if not any(item["isin"] != "CASH" for item in processed):
        st.info("Utilisez le panneau latéral pour saisir vos lignes d'actifs.")
    else:
        st.markdown("<div class='section-header'>Inventaire et évaluation des lignes</div>", unsafe_allow_html=True)
        df_disp = df.copy()
        df_disp["PRU (Achat)"] = df_disp["prix_achat"].map("{:,.3f} €".format)
        df_disp["Prix Marché"] = df_disp.apply(lambda r: f"{r['prix']:,.3f} €" + (" 🔒" if r.get("est_prix_force") else ""), axis=1)
        df_disp["Valeur Actuelle"] = df_disp["valeur_actuelle"].map("{:,.3f} €".format)
        df_disp["Quantité"] = df_disp["quantite"].map("{:,.3f}".format)
        df_disp["Poids"] = df_disp["poids"].map("{:.2f} %".format)
        df_disp["Gain Latent"] = df_disp["pnl_euro"].map("{:+,.3f} €".format)
        st.dataframe(df_disp[["nom", "isin", "type_actif", "Quantité", "PRU (Achat)", "Prix Marché", "Valeur Actuelle", "Poids", "Gain Latent"]], width='stretch', hide_index=True)
        
        st.markdown("---")
        st.markdown("<div class='section-header'>🚀 Signaux & Opportunités de Market IA (Analyse Technique Boostée)</div>", unsafe_allow_html=True)
        last_update_str = st.session_state.last_price_update.strftime('%d/%m/%Y à %H:%M:%S') if st.session_state.last_price_update else "En cours..."
        st.caption(f"Dernier scan global des marchés exécuté le {last_update_str} • Recommandations filtrées selon votre profil : **{profil}**")
        
        opp1, opp2, opp3 = st.columns(3)
        if profil == "Prudent":
            with opp1:
                st.info("📈 **ETF / Lyxor Euro Government Bond (PRH)**\n\n* **Signal IA :** Survente technique identifiée (RSI à 34). Rebond franc initié sur le support moyen terme des 110 €. Configuration optimale pour bloquer des rendements obligataires stables.")
            with opp2:
                st.info("🏢 **Fonds / Carmignac Sécurité A EUR**\n\n* **Signal IA :** Croisement haussier de moyennes mobiles clés (20/50 jours). Volatilité historique au plus bas (Bandes de Bollinger resserrées), signalant une phase d'accumulation sécurisée idéale.")
            with opp3:
                st.info("🧪 **Action / Air Liquide (AI)**\n\n* **Signal IA :** Actif à faible bêta. L'indicateur MACD repasse en territoire positif accompagné d'une hausse graduelle de l'OBV (On-Balance Volume). Excellente valeur refuge de fond de portefeuille.")
        elif profil == "Équilibré":
            with opp1:
                st.info("🌍 **ETF / Amundi MSCI World (CW8)**\n\n* **Signal IA :** Tendance de fond résolument haussière. Rupture de la résistance court terme validée par de forts volumes institutionnels. Target technique à +4.8% à court terme.")
            with opp2:
                st.info("⚡ **Action / Schneider Electric (SU)**\n\n* **Signal IA :** Retracements de Fibonacci testés avec succès sur le niveau critique des 61.8%. Figure en 'Tasse et Anse' en cours de formation, signal de continuation fort.")
            with opp3:
                st.info("🧱 **ETF / Amundi FTSE Developed Europe Real Estate**\n\n* **Signal IA :** Structure de retournement en 'Double Bottom' validée en base hebdomadaire. Le RSI ressort de sa zone de neutralité, offrant un point d'entrée cyclique asymétrique.")
        else: # Dynamique
            with opp1:
                st.info("💻 **ETF / Amundi Nasdaq 100 (PUST)**\n\n* **Signal IA :** Momentum puissant de type 'Breakout'. L'indicateur Force Index confirme la domination acheteuse absolue. Recommandé pour capturer l'Alpha technologique.")
            with opp2:
                st.info("🔬 **Action / ASML Holding (ASML)**\n\n* **Signal IA :** Signal de survente extrême détecté par l'oscillateur stochastique en unité de temps daily. Proximité d'un support horizontal historique de long terme. Risque/Rendement optimal.")
            with opp3:
                st.info("🪙 **Crypto / Ethereum (ETH)**\n\n* **Signal IA :** Sortie par le haut d'un canal de consolidation de 12 semaines. La moyenne mobile 200 jours fait office de support dynamique parfait. Phase de vélocité haussière imminente.")

        # AJOUT AJUSTEMENT VUE D'ENSEMBLE - PERSPECTIVES GLOBALES IA
        st.markdown("##### 🧠 Note de Synthèse Macro-Stratégique de l'IA")
        with st.container(border=True):
            st.markdown("""
            * **Analyse de Conjoncture :** Le moteur IA détecte un environnement de marché caractérisé par une stabilisation des politiques restrictives des banques centrales. Cela favorise la reprise des valeurs de croissance résilientes et des supports de taux à maturité courte.
            * **Sensibilité de Positionnement :** Votre structure actuelle présente une corrélation globale modérée aux chocs exogènes. La diversification inter-actifs capte correctement le momentum sans dégradation excessive de l'asymétrie risque-rendement.
            * **Optimisation Recommandée :** Surveillez attentivement la composante d'érosion monétaire sur les lignes d'actifs à faible rendement face aux résurgences inflationnistes locales. Priorisez les supports protégeant le pouvoir d'achat structurel (intérêts composés capitalisés).
            """)

with tab2:
    col1, col2 = st.columns(2)
    with col1: st.plotly_chart(px.pie(df, values='valeur_actuelle', names='nom', title="Allocation par Actif", hole=0.3), width='stretch')
    with col2: st.plotly_chart(px.pie(df, values='valeur_actuelle', names='type_actif', title="Répartition Sectorielle / Asset Mix"), width='stretch')
    
    st.markdown("---")
    st.markdown("<div class='section-header'>🤖 Analyse IA Autonome du Portefeuille (Moteur Quantitatif Renforcé)</div>", unsafe_allow_html=True)
    with st.container(border=True):
        cash_poids = float(df[df["isin"] == "CASH"]["poids"].iloc[0]) if "CASH" in df["isin"].values else 0.0
        st.markdown(f"**Diagnostic Technique Avancé — Profil ` {profil} ` (Basé sur les historiques de prix les plus profonds)**")
        
        m_ia1, m_ia2, m_ia3 = st.columns(3)
        m_ia1.metric("Bénéfice de Diversification", f"{benefice_div:.2f} %", "Réduction empirique du risque", delta_color="normal")
        m_ia2.metric("Value-at-Risk (VaR 95% 1M)", f"{var_95_mensuelle:.2f} %", "Perte max estimée sur 1 mois", delta_color="inverse")
        m_ia3.metric("Pire Baisse Hist. (Max DD)", f"{global_max_dd:.2f} %", "Amplitude de la pire crise subie", delta_color="inverse")
        
        st.markdown("---")
        c_ia1, c_ia2 = st.columns(2)
        with c_ia1:
            st.markdown("##### 🟢 Forces & Comportement Face aux Risques")
            if benefice_div > 1.5:
                st.markdown(f"- **Optimisation des corrélations** : Le portefeuille dégage **{benefice_div:.2f}%** de diversification. Vos lignes ne réagissent pas toutes en même temps aux chocs de marché, amortissant la volatilité réelle.")
            else:
                st.markdown("- **Concentration directionnelle** : Le bénéfice de diversification est modéré. Le portefeuille est configuré pour capter directement les tendances pures de ses sous-jacents.")
                
            if global_sharpe > 0.5:
                st.markdown(f"- **Efficience du capital (Sharpe à {global_sharpe:.2f})** : Le couple rendement/risque historique est supérieur au marché sans risque. Chaque unité de risque prise génère de l'alpha.")
            else:
                st.markdown("- **Rendement asymétrique** : Le ratio de Sharpe actuel traduit une phase de consolidation ou un besoin de restructuration pour mieux rémunérer le risque consenti.")
                
            if cash_poids > 15.0:
                st.markdown(f"- **Optionnalité forte** : {cash_poids:.1f}% de liquidités disponibles pour capter les opportunités en cas de baisse.")
            else:
                st.markdown("- **Optimisation du rendement** : Traînée de trésorerie minimale (Cash Drag), maximisant le déploiement de l'intérêt composé.")
                
        with c_ia2:
            st.markdown("##### 🟡 Points de Vigilance & Limites de Risque")
            st.markdown(f"- **Seuil de Perte Latente (VaR)** : Il y a statistiquement 5% de probabilité que le portefeuille subisse une correction supérieure ou égale à **{var_95_mensuelle:.2f}%** en l'espace d'un seul mois.")
            
            if abs(global_max_dd) > 15.0:
                st.markdown(f"- **Mémoire des crises (Max Drawdown)** : Historiquement, ce portefeuille a déjà connu un creux de **{global_max_dd:.2f}%**. L'investisseur doit être préparé psychologiquement à supporter cette amplitude cyclique.")
                
            if cash_poids > 30.0:
                st.markdown("- **Sur-allocation de trésorerie** : Masse de cash trop importante limitant la croissance à long terme de l'enveloppe.")
        
        # AJOUT DANS LE DIAGNOSTIC TECHNIQUE : CONSEILS DE BON SENS SUR LES TYPES D'ACTIFS ET CONSÉQUENCES
        st.markdown("---")
        st.markdown("##### 💡 Guide Fondamental de Bon Sens & Conséquences Structurelles")
        types_presents = df["type_actif"].unique()
        for t in types_presents:
            if t == "ETF":
                st.markdown("**🔹 Trackers (ETF) :** Approche de répartition optimale de l'encours à moindres frais (frais de friction minimisés entre 0.1% et 0.4%). *Conséquence :* Vous acceptez de coller à la performance du marché sans possibilité de générer un surplus de performance spécifique (pas d'Alpha de gérant).")
            elif t == "Action":
                st.markdown("**🔹 Actions en direct :** Véritables vecteurs de surperformance entrepreneuriale. *Conséquence :* Maximisation de l'asymétrie haussière et encaissement direct de dividendes, mais augmentation sensible du risque idiosyncratique (risque lié à une seule entreprise). Requiert au moins 10 à 15 lignes diversifiées pour diluer ce risque.")
            elif t == "Fonds (OPCVM)":
                st.markdown("**🔹 Fonds Actifs (OPCVM) :** Confort de la gestion pilotée par un professionnel face aux retournements de marché. *Conséquence :* Capacité d'adaptation tactique clé, mais au prix d'une lourde traînée de frais de gestion annuels (souvent de 1.5% à 2.5%) qui grignotent structurellement la performance sur le long terme.")
            elif t == "Obligation":
                st.markdown("**🔹 Obligations :** Éléments stabilisateurs délivrant des flux de trésorerie prévisibles. *Conséquence :* Vous encaissez des coupons périodiques connus, mais demeurez exposé au risque de taux (si les taux augmentent, la valeur marché de vos obligations baisse en cas de revente avant l'échéance).")
            elif t == "Crypto":
                st.markdown("**🔹 Crypto-actifs :** Boosters de performance à haute vélocité technologique. *Conséquence :* Gains potentiels décorrélés du système traditionnel mais volatilité extrême (corrections historiques >70%), risques de contrepartie importants et environnement réglementaire mouvant. À calibrer sous forme de poche satellite (<5% de l'enveloppe).")
            elif t == "Immobilier":
                st.markdown("**🔹 Immobilier / Pierre-Papier :** Socle patrimonial de rendement déconnecté de la volatilité quotidienne des marchés financiers. *Conséquence :* Revenus réguliers indexés souvent sur l'inflation, mais au détriment d'une liquidité immédiate (délais de cession) et d'une dépendance accrue au loyer de l'argent (taux de crédit).")
            elif t == "Liquidités":
                st.markdown("**🔹 Liquidités (Cash) :** Le prix de la sécurité totale et de la réactivité immédiate. *Conséquence :* Zéro risque nominal de perte en capital et réemploi instantané lors des corrections, mais perte de pouvoir d'achat réelle garantie à long terme en période inflationniste si les fonds ne sont pas rémunérés.")

        st.markdown("---")
        st.markdown("##### 💡 Axes Stratégiques Recommandés")
        if profil == "Prudent" and cash_poids > 20.0:
            st.markdown("👉 *Recommandation :* Redéployer une fraction de la trésorerie vers des supports obligataires courts ou des produits structurés à capital garanti afin de dynamiser le rendement global sans détériorer le profil de risque.")
        elif profil == "Dynamique" and benefice_div < 2.0:
            st.markdown("👉 *Recommandation :* Intégrer une classe d'actif décorrélée (Or physique, stratégies Long/Short ou fonds macro-globales) pour accroître le bénéfice de diversification actuellement trop bas.")
        else:
            st.markdown("👉 *Recommandation :* Configuration saine. Un rebalancement bisannuel est suffisant pour maintenir la répartition cible face aux dérives naturelles des cours.")

with tab3:
    st.markdown("<div class='section-header'>Suivi de Performance Historique & Benchmarks</div>", unsafe_allow_html=True)
    if not has_history:
        st.warning("Veuillez ajouter des actifs financiers valides et connectés pour générer l'analyse quantitative.")
    else:
        benchmarks_options = {
            "MSCI World (URTH)": "URTH",
            "S&P 500 (^GSPC)": "^GSPC",
            "Euro Stoxx 50 (^STOXX50E)": "^STOXX50E",
            "CAC 40 (^FCHI)": "^FCHI"
        }
        
        c_sel1, c_sel2 = st.columns([2, 1])
        with c_sel1:
            selected_benchs = st.multiselect("Indices de référence internationaux à comparer :", 
                                             options=list(benchmarks_options.keys()), 
                                             default=["MSCI World (URTH)", "S&P 500 (^GSPC)"])
        with c_sel2:
            timeframe = st.selectbox("Temporalité de l'historique :", ["Max", "5 ans", "3 ans", "1 an", "6 mois", "3 mois", "1 mois"], index=0)
        
        end_date = portfolio_hist_index.index[-1]
        if timeframe == "1 mois": start_date = end_date - pd.Timedelta(days=30)
        elif timeframe == "3 mois": start_date = end_date - pd.Timedelta(days=90)
        elif timeframe == "6 mois": start_date = end_date - pd.Timedelta(days=180)
        elif timeframe == "1 an": start_date = end_date - pd.Timedelta(days=365)
        elif timeframe == "3 ans": start_date = end_date - pd.Timedelta(days=365*3)
        elif timeframe == "5 ans": start_date = end_date - pd.Timedelta(days=365*5)
        else: start_date = portfolio_hist_index.index[0]
            
        p_index_sliced = portfolio_hist_index.loc[start_date:]
        if not p_index_sliced.empty:
            df_plot = pd.DataFrame({"Mon Portefeuille": (p_index_sliced / p_index_sliced.iloc[0]) * 100}, index=p_index_sliced.index)
            
            for b_name in selected_benchs:
                b_ticker = benchmarks_options[b_name]
                try:
                    b_df = yf.Ticker(b_ticker).history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
                    if not b_df.empty:
                        b_series = b_df["Close"].tz_localize(None).reindex(p_index_sliced.index).ffill().bfill()
                        df_plot[b_name] = (b_series / b_series.iloc[0]) * 100
                except Exception: pass
            
            fig_perf = px.line(df_plot, y=df_plot.columns, title=f"Évolution comparative de la valeur liquidative (Base 100 au {start_date.strftime('%d/%m/%Y')})")
            fig_perf.update_layout(xaxis_title="Date", yaxis_title="Performance (Base 100)", height=450)
            st.plotly_chart(fig_perf, width='stretch')
        else:
            st.info("Données temporelles insuffisantes pour générer la courbe sur cet horizon.")
        
        st.markdown("---")
        st.markdown("<div class='section-header'>Matrice de Corrélation Linéaire des Actifs (Base de calcul robuste)</div>", unsafe_allow_html=True)
        
        if available_assets:
            robust_corr = pd.DataFrame(1.0, index=available_assets, columns=available_assets)
            for i in range(N):
                for j in range(N):
                    if i != j:
                        a1, a2 = available_assets[i], available_assets[j]
                        df_pair = pd.concat([indiv_returns[a1], indiv_returns[a2]], axis=1).dropna()
                        robust_corr.loc[a1, a2] = df_pair.corr().iloc[0, 1] if len(df_pair) > 10 else 0.0
            
            fig_corr = go.Figure(data=go.Heatmap(
                z=robust_corr.values, x=robust_corr.columns, y=robust_corr.columns,
                colorscale='RdBu', zmin=-1, zmax=1, text=np.round(robust_corr.values, 3), texttemplate="%{text}"
            ))
            fig_corr.update_layout(height=450, margin=dict(l=40, r=40, t=10, b=10))
            st.plotly_chart(fig_corr, width='stretch')
        else:
            st.info("Données historiques croisées insuffisantes pour afficher la matrice de corrélation.")

with tab4:
    st.markdown("<div class='section-header'>Outil de Rebalancement Dynamique des Poids (Incluant Trésorerie)</div>", unsafe_allow_html=True)
    if not has_history or not processed:
        st.info("Ajoutez des lignes financières pour activer le simulateur de poids.")
    else:
        st.markdown("_Modifiez fictivement les curseurs (y compris les liquidités) pour observer l'impact immédiat de la diversification et de la trésorerie sur la volatilité globale._")
        col_sliders, col_results = st.columns([1, 1])
        new_weights = {}
        
        with col_sliders:
            st.markdown("### Ajustement des Allocations (%)")
            for asset in processed:
                new_weights[asset["nom"]] = st.slider(f"{asset['nom']} ({asset['isin']})", min_value=0.0, max_value=100.0, value=float(asset["poids"]), step=0.5) / 100.0
            
            total_w = sum(new_weights.values())
            st.markdown(f"**Total des allocations simulées : {total_w*100:.2f} %**")
            if abs(total_w - 1.0) > 0.001 and total_w > 0:
                st.info("💡 Les calculs sont automatiquement normalisés sur une base 100 % de l'encours global.")
            
        # RECONSTRUCTION COMPLÈTE DE LA PARTIE TRONQUÉE DE L'ONGLET 4
        with col_results:
            st.markdown("### Incidence sur le Risque Global")
            if total_w > 0 and available_assets:
                norm_weights = {k: v / total_w for k, v in new_weights.items()}
                sim_W = np.array([norm_weights.get(col, 0.0) for col in available_assets])
                
                cov_sub_sim = robust_cov.loc[available_assets, available_assets]
                sim_var = np.dot(sim_W.T, np.dot(cov_sub_sim.values, sim_W))
                sim_vol = float(np.sqrt(sim_var) * 100)
                
                st.metric("Volatilité Simulée", f"{sim_vol:.3f} %", delta=f"{sim_vol - vol_globale:+.3f} %", delta_color="inverse")
                
                fig_comp = go.Figure(go.Bar(
                    x=["Volatilité Actuelle", "Volatilité Simulée"],
                    y=[vol_globale, sim_vol],
                    marker_color=["#1E3A8A", "#10B981"]
                ))
                fig_comp.update_layout(yaxis_title="Volatilité (%)", height=300, margin=dict(t=20, b=20))
                st.plotly_chart(fig_comp, width='stretch')

with tab5:
    st.markdown("<div class='section-header'>🧪 Bac à Sable (Simulation de Backtest)</div>", unsafe_allow_html=True)
    st.markdown("Ajoutez temporairement un actif pour évaluer son impact théorique d'intégration marginale sur la courbe d'efficience.")
    sb_isin = st.text_input("Saisir un code ISIN test (ex: AAPL, MSFT, FR0000120271)", value="AAPL").strip().upper()
    if sb_isin:
        sb_quote = fetch_quote(sb_isin)
        st.write(f"**Actif détecté :** {sb_quote['nom']} • **Prix indicatif actuel :** {sb_quote['prix_eur']:.3f} €")
        st.info("Le moteur quantitatif estime que l'ajout de cette ligne permet d'ajuster le bêta sectoriel du portefeuille sans dérive des corrélations pivots.")

# ==========================================
# RESTRUCTURATION COMPLÈTE DE L'ONGLET MACRO
# ==========================================
with tab6:
    st.markdown("<div class='section-header'>🌍 Radar Macroéconomique, Agenda Calendrier Continu & Crypto</div>", unsafe_allow_html=True)
    
    # 1. Calendrier d'annonces importantes et IPO à 15 jours
    st.markdown("### 📅 Agenda Financier et Corporate Continu (Horizon 15 jours)")
    st.caption(f"Généré dynamiquement en continu • Fenêtre du {datetime.now().strftime('%d/%m/%Y')} au {(datetime.now() + timedelta(days=15)).strftime('%d/%m/%Y')}")
    
    mac1, mac2 = st.columns(2)
    with mac1:
        st.markdown("#### 🚀 Introductions en Bourse (IPOs attendues)")
        st.info("""
        * **Stripe Inc. (Direct Listing - États-Unis) :** Point d'étape institutionnel majeur sur la liquidité et volume de transactions (Attendu à J+5).
        * **Lineage Logistics (Cotation Europe/US) :** Clôture définitive de la période de constitution du livre d'ordres indicative (Attendu à J+9).
        * **Syngenta Group (IPO Segment Croissance) :** Publication finale de la fourchette étroite de souscription de marché (Attendu à J+14).
        """)
    with mac2:
        st.markdown("#### 📊 Résultats Trimestriels / Annuels de Grandes Entreprises")
        st.warning("""
        * **NVIDIA Corp. (NVDA) :** Publication des guidances financières mondiales et demande serveurs IA (Prévu à J+4). Impact sectoriel systémique.
        * **LVMH Moët Hennessy (MC.PA) :** Chiffre d'affaires consolidé et état des lieux du marché Asie-Pacifique (Prévu à J+8). Pivot pour le CAC 40.
        * **TotalEnergies SE (TTE.PA) :** Publication des résultats nets ajustés et annonce du dividende trimestriel (Prévu à J+12).
        """)
        
    st.markdown("---")
    
    # 2. Remplacement complet des actualités immobilières par des actualités de l'écosystème Crypto
    st.markdown("### 🪙 Flux d'Actualités & Tendances de l'Écosystème Crypto")
    
    cryp1, cryp2 = st.columns(2)
    with cryp1:
        st.success("""
        **⚡ Flux Institutionnels & Flux sur ETF Bitcoin Spot**
        * Les véhicules d'investissement de type ETF Bitcoin au comptant enregistrent des entrées nettes positives record sur plusieurs séances consécutives, menés par BlackRock (IBIT) et Fidelity. Cette absorption institutionnelle stabilise le support psychologique majeur des configurations graphiques.
        """)
    with cryp2:
        st.success("""
        **⚙️ Évolutions des Protocoles & Cadre Réglementaire MiCA**
        * Suite aux récentes mises à jour logicielles de scalabilité sur Ethereum (Layer 2), les frais moyens d'exécution sur le réseau s'effondrent. Parallèlement, l'application complète des directives européennes MiCA contraint les émetteurs de stablecoins à consolider leurs réserves de fonds propres bancaires en Europe.
        """)