# Déploiement Railway — Guide Complet

## ÉTAPE 1 — Préparer le dépôt GitHub

```bash
cd saas-backend
git init
git add .
git commit -m "feat: initial SaaS backend"
git remote add origin https://github.com/TON_USERNAME/saas-backend.git
git push -u origin main
```

---

## ÉTAPE 2 — Créer le projet Railway

1. Aller sur https://railway.app → **New Project**
2. Choisir **Deploy from GitHub repo**
3. Sélectionner le repo `saas-backend`
4. Railway détecte le `Dockerfile` automatiquement

---

## ÉTAPE 3 — Ajouter PostgreSQL

1. Dans le projet Railway → **Add Service** → **Database** → **PostgreSQL**
2. Railway injecte automatiquement la variable `DATABASE_URL`

---

## ÉTAPE 4 — Ajouter Redis

1. **Add Service** → **Database** → **Redis**
2. Railway injecte automatiquement `REDIS_URL`

---

## ÉTAPE 5 — Configurer les variables d'environnement

Dans le service **API** → **Variables** → ajouter :

```
SECRET_KEY          = (générer : python -c "import secrets; print(secrets.token_hex(32))")
DEBUG               = false
BASE_URL            = https://VOTRE-APP.railway.app
ALLOWED_ORIGINS     = https://votre-frontend.com

FLEXPAY_TOKEN       = votre_token
FLEXPAY_MERCHANT    = votre_merchant
FLEXPAY_WEBHOOK_SECRET = votre_secret

STRIPE_SECRET_KEY   = sk_live_...
STRIPE_WEBHOOK_SECRET = whsec_...

WHATSAPP_TOKEN      = EAA...
WHATSAPP_PHONE_NUMBER_ID = 123456789
WHATSAPP_VERIFY_TOKEN = mon_token

TWILIO_ACCOUNT_SID  = AC...
TWILIO_AUTH_TOKEN   = ...
TWILIO_FROM_NUMBER  = +12015551234

ANTHROPIC_API_KEY   = sk-ant-...
```

---

## ÉTAPE 6 — Lancer les migrations

Via Railway CLI :
```bash
npm install -g @railway/cli
railway login
railway link          # sélectionner le projet
railway run alembic upgrade head
```

Ou directement dans le Dockerfile (déjà configuré) :
```
CMD = alembic upgrade head && uvicorn ...
```

---

## ÉTAPE 7 — Ajouter le service Worker Celery

1. **Add Service** → **GitHub Repo** (même repo)
2. Dans **Settings** → **Start Command** :
   ```
   celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2 -Q default,payments,notifications
   ```
3. Copier toutes les variables d'environnement depuis le service API

---

## ÉTAPE 8 — Configurer les Webhooks externes

### FlexPay
- Dashboard FlexPay → Paramètres → Webhook URL :
  `https://VOTRE-APP.railway.app/api/v1/payments/webhook/flexpay`

### Stripe
- Dashboard Stripe → Developers → Webhooks → Add endpoint :
  `https://VOTRE-APP.railway.app/api/v1/payments/webhook/stripe`
  - Events : `checkout.session.completed`, `payment_intent.succeeded`

### WhatsApp (Meta)
- Meta Business Suite → WhatsApp → Configuration → Webhook :
  - Callback URL : `https://VOTRE-APP.railway.app/api/v1/notifications/webhook/whatsapp`
  - Verify Token : (même que `WHATSAPP_VERIFY_TOKEN`)
  - S'abonner à : `messages`

---

## ÉTAPE 9 — Vérifier le déploiement

```bash
# Health check
curl https://VOTRE-APP.railway.app/health

# Réponse attendue
{"status": "ok", "version": "1.0.0", "app": "Livroto SaaS"}
```

---

## Structure des URLs API

```
POST   /api/v1/auth/register          → Inscription
POST   /api/v1/auth/login             → Connexion
POST   /api/v1/auth/refresh           → Refresh token
POST   /api/v1/auth/otp/send          → Envoyer OTP
POST   /api/v1/auth/otp/verify        → Vérifier OTP
GET    /api/v1/auth/me                → Profil connecté

GET    /api/v1/products               → Liste produits
POST   /api/v1/products               → Créer produit (manager+)
GET    /api/v1/products/alerts/low-stock → Alertes stock

POST   /api/v1/orders                 → Créer commande
GET    /api/v1/orders                 → Liste commandes
PATCH  /api/v1/orders/{id}/status     → Mettre à jour statut

POST   /api/v1/payments/flexpay/initiate   → Payer Mobile Money
POST   /api/v1/payments/stripe/checkout    → Payer par carte
POST   /api/v1/payments/webhook/flexpay    → Webhook FlexPay
POST   /api/v1/payments/webhook/stripe     → Webhook Stripe

POST   /api/v1/notifications/send          → Envoyer message
POST   /api/v1/notifications/broadcast     → Envoi en masse
POST   /api/v1/notifications/webhook/whatsapp → Messages entrants

POST   /api/v1/ai/support                  → Support client IA
POST   /api/v1/ai/marketing/generate       → Message marketing
POST   /api/v1/ai/analytics/sales          → Analyse ventes
POST   /api/v1/ai/finance/report           → Rapport financier

POST   /api/v1/location/update             → Position GPS livreur
GET    /api/v1/location/order/{id}/track   → Suivi commande
GET    /api/v1/location/rider/{id}/current → Position actuelle
```

---

## Coûts Railway estimés (plan Starter)

| Service        | Coût/mois |
|---------------|-----------|
| API FastAPI    | ~5 USD    |
| PostgreSQL     | ~5 USD    |
| Redis          | ~3 USD    |
| Worker Celery  | ~3 USD    |
| **Total**      | **~16 USD/mois** |
