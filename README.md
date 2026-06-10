# Cabinet Honoré & Associés - Gestion de Patrimoine Pro

Application Streamlit pour l'ingénierie patrimoniale et l'analyse quantitative avancée de portefeuille.

## 🚀 Démarrage Local

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Lancer l'application
streamlit run streamlit_app.py
```

L'application sera accessible à : `http://localhost:8501`

## 📤 Déploiement sur Streamlit Cloud

### Étapes de publication :

1. **Créer un compte Streamlit Cloud** (gratuit)
   - Accédez à [share.streamlit.io](https://share.streamlit.io)
   - Connectez-vous avec votre compte GitHub

2. **Préparer le dépôt GitHub**
   - Assurez-vous que votre code est poussé sur GitHub
   - Le dépôt doit contenir :
     - `streamlit_app.py` (fichier principal)
     - `requirements.txt` (dépendances)

3. **Déployer l'application**
   - Cliquez sur "New app" dans Streamlit Cloud
   - Sélectionnez le repository et la branche
   - Indiquez le chemin vers le fichier : `streamlit_app.py`
   - Cliquez sur "Deploy"

4. **Configuration post-déploiement** (optionnel)
   - Les secrets sensibles vont dans `.streamlit/secrets.toml` (non versionnée)
   - Streamlit Cloud gère automatiquement `config.toml`

## 📋 Configuration

Le fichier `.streamlit/config.toml` définit :
- **Thème** : Couleurs et typographie personnalisées
- **Serveur** : Limites d'upload (200 MB) et protections de sécurité

## 📦 Dépendances Principales

- `streamlit` : Framework web
- `plotly` : Visualisations interactives
- `yfinance` : Données financières Yahoo Finance
- `beautifulsoup4` : Web scraping de Boursorama
- `pandas` & `numpy` : Analyse quantitative

## 🔧 Troubleshooting

### Le bouton "Forcer la mise à jour" ne fonctionne pas
→ Vérifiez votre connexion Internet et les délais d'API

### Les graphiques ne s'affichent pas
→ Assurez-vous que `plotly` est à jour : `pip install --upgrade plotly`

### Erreur "use_container_width"
→ Déjà corrigé ! Utilise maintenant `width='stretch'`

## 📧 Support

Pour toute question sur Streamlit Cloud, consultez la [documentation officielle](https://docs.streamlit.io/streamlit-community-cloud)
