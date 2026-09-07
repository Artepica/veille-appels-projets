# Veille des appels à projets — Art'Epica

Cet outil cherche automatiquement les appels à projets qui ressemblent à
« Regards Connectés » (jeunesse, numérique responsable, ruralité, art et
photographie, financements de fondations ou de caisses locales comme le
Crédit Agricole) et génère :

- un **tableau de bord HTML** (`data/dashboard.html`) à ouvrir dans un navigateur
- un **email récapitulatif** des nouveautés à chaque exécution

## ⚠️ Important à savoir avant de commencer

Ce script doit être **exécuté depuis votre propre ordinateur ou un petit
serveur** (pas depuis cette conversation). Pour qu'il tourne automatiquement
chaque semaine, il faut le **planifier** (cron / Planificateur de tâches
Windows — voir plus bas). Ce n'est pas un site web en ligne accessible de
partout par défaut : c'est un fichier HTML généré localement. Si vous
voulez à terme un vrai site accessible en ligne (ex. pour toute l'équipe
d'Art'Epica), on peut héberger ce même fichier sur GitHub Pages ou Netlify
gratuitement — dites-le-moi et je vous prépare cette étape en plus.

## Structure du projet

```
veille_project/
├── veille_appels_projets.py   ← le script principal
├── requirements.txt
├── netlify.toml                ← config Netlify (dossier publié = "site")
├── README.md                   ← ce fichier
├── site/                       ← généré automatiquement, publié sur Netlify
│   └── index.html
└── data/
    ├── dashboard.html           ← copie locale du tableau de bord
    └── historique.json          ← mémoire des appels déjà vus
```

## 1. Installation

```bash
python3 -m venv venv
source venv/bin/activate      # sous Windows : venv\Scripts\activate
pip install requests beautifulsoup4
```

## 2. Configuration

Toutes les informations sensibles passent par des **variables d'environnement**
(jamais écrites dans le code, pour votre sécurité).

### a) Aides-Territoires (optionnel mais recommandé)

1. Créez un compte gratuit sur https://aides-territoires.beta.gouv.fr/comptes/inscription/
2. Demandez un accès à l'API depuis votre espace utilisateur (rubrique API)
3. Renseignez le token reçu :

```bash
export VEILLE_AT_TOKEN="votre_token_ici"
```

Sans ce token, cette source est simplement ignorée — le script continue de
fonctionner avec Carenews et la recherche web.

### b) Email récapitulatif

Exemple avec une adresse Gmail (créez un **mot de passe d'application**
dans les paramètres de sécurité Google — n'utilisez jamais votre mot de
passe principal) :

```bash
export VEILLE_EMAIL_HOTE="smtp.gmail.com"
export VEILLE_EMAIL_PORT="587"
export VEILLE_EMAIL_USER="votreadresse@gmail.com"
export VEILLE_EMAIL_PASSWORD="votre_mot_de_passe_application"
export VEILLE_EMAIL_TO="destinataire@exemple.fr"
```

Pour un autre fournisseur (Outlook, OVH, etc.), remplacez l'hôte et le port
par ceux indiqués dans les paramètres SMTP de votre messagerie.

Pour que ces variables soient actives à chaque exécution planifiée (cron),
mettez-les dans un fichier `.env` chargé par le script de planification,
ou ajoutez-les directement dans votre `crontab` / tâche planifiée.

## 3. Lancer le script manuellement

```bash
python3 veille_appels_projets.py
```

Puis ouvrez `data/dashboard.html` dans votre navigateur.

## 4. Planifier une exécution automatique hebdomadaire

### macOS / Linux (cron)

```bash
crontab -e
```

Ajoutez (exécution tous les lundis à 8h) :

```
0 8 * * 1 cd /chemin/vers/veille_project && /chemin/vers/venv/bin/python3 veille_appels_projets.py >> log.txt 2>&1
```

### Windows (Planificateur de tâches)

1. Ouvrir "Planificateur de tâches" → "Créer une tâche de base"
2. Déclencheur : chaque semaine, le jour et l'heure de votre choix
3. Action : démarrer un programme →
   - Programme : chemin vers `python.exe` (dans `venv\Scripts\`)
   - Arguments : `veille_appels_projets.py`
   - Démarrer dans : le dossier du projet

## 5. Mise en ligne sur Netlify (accessible depuis n'importe où)

Le script génère automatiquement un dossier `site/` (avec un `index.html`
dedans) qui est exactement ce que Netlify a besoin de publier. Deux façons
de faire, de la plus simple à la plus automatique :

### Option A — Manuelle, en 2 minutes, aucun compte développeur requis

1. Créez un compte gratuit sur https://app.netlify.com
2. Lancez le script une première fois (`python3 veille_appels_projets.py`)
   pour générer le dossier `site/`
3. Sur Netlify, cliquez "Add new site" → "Deploy manually"
4. Glissez-déposez le dossier `site/` dans la zone prévue
5. Netlify vous donne une URL du type `https://nom-aleatoire.netlify.app`

Pour republier après chaque nouvelle exécution du script, il suffit de
refaire un glisser-déposer du dossier `site/` mis à jour. C'est manuel mais
zéro configuration.

### Option B — Automatique, publication à chaque exécution du script

Le script sait publier lui-même sur Netlify via leur API (pas besoin
d'installer Node.js ni la CLI Netlify).

1. Faites l'étape 1 à 4 de l'Option A une seule fois, pour créer le site
2. Récupérez son **Site ID** : sur Netlify, ouvrez le site → **Site
   configuration** → **General** → copiez le "Site ID"
3. Créez un **jeton d'accès personnel** : cliquez sur votre avatar (en haut
   à droite) → **User settings** → **Applications** → **New access token**
4. Renseignez les deux variables d'environnement :

```bash
export VEILLE_NETLIFY_TOKEN="votre_jeton_ici"
export VEILLE_NETLIFY_SITE_ID="votre_site_id_ici"
```

5. Relancez le script : `python3 veille_appels_projets.py`

À partir de là, **chaque exécution** (y compris via cron/planificateur —
voir § 4) régénère le tableau de bord *et* le republie automatiquement sur
votre URL Netlify. Vous n'avez plus rien à faire manuellement.

> Astuce : si vous voulez un nom de domaine personnalisé (ex.
> `veille.artepica.fr`), c'est gratuit à configurer dans Netlify une fois
> le site créé (**Domain settings** → **Add a domain**) — mais il faut
> posséder ce nom de domaine par ailleurs.

### Option C — Exécution dans le cloud via GitHub Actions (recommandé si vous voulez piloter la veille depuis plusieurs ordinateurs, y compris publics)

Avec les options A et B, le script tourne sur **votre** ordinateur : les
identifiants (Netlify, email...) doivent y être configurés, et c'est cet
ordinateur qui doit être allumé pour que la veille planifiée se déclenche.

Avec GitHub Actions, le script tourne **dans le cloud**, gratuitement :
- Les identifiants sont stockés **une seule fois**, chiffrés dans GitHub —
  jamais sur un ordinateur, encore moins un poste public.
- La veille se déclenche chaque semaine **même si aucun ordinateur n'est
  allumé**.
- Pour la relancer manuellement depuis n'importe quel poste, il suffit de
  se connecter à votre compte GitHub dans un navigateur et cliquer un
  bouton — aucune information sensible ne transite par cet ordinateur.

Le fichier `.github/workflows/veille.yml` est déjà inclus dans le projet.
Étapes de mise en place (à faire une seule fois) :

1. Créez un compte gratuit sur https://github.com si besoin
2. Créez un nouveau dépôt (ex. `veille-appels-projets`), puis envoyez-y le
   projet depuis votre ordinateur :

```bash
git init
git add .
git commit -m "Premier envoi"
git branch -M main
git remote add origin https://github.com/VOTRE_COMPTE/veille-appels-projets.git
git push -u origin main
```

3. Sur la page du dépôt : **Settings → Secrets and variables → Actions →
   New repository secret**. Ajoutez, un par un (nom exact à gauche, valeur
   à droite) :

   - `VEILLE_NETLIFY_TOKEN`, `VEILLE_NETLIFY_SITE_ID`
   - `VEILLE_EMAIL_HOTE`, `VEILLE_EMAIL_PORT`, `VEILLE_EMAIL_USER`,
     `VEILLE_EMAIL_PASSWORD`, `VEILLE_EMAIL_TO`
   - `VEILLE_AT_TOKEN` (optionnel, si vous avez un token Aides-Territoires)

4. C'est fini. La veille se déclenche désormais automatiquement chaque
   lundi. Pour la lancer manuellement depuis n'importe quel ordinateur :
   ouvrez le dépôt sur GitHub → onglet **Actions** → cliquez sur "Veille
   des appels à projets" → bouton **Run workflow**.

Avec cette option, la section 4 (planification cron / Planificateur de
tâches) devient inutile : plus besoin que votre PC personnel soit allumé
ou configuré.

## 6. Ajuster les mots-clés et les sources

Tout se règle en haut du fichier `veille_appels_projets.py` :

- `MOTS_CLES_THEME` / `MOTS_CLES_FINANCEURS` : les mots qui définissent la
  pertinence d'un résultat
- `REQUETES_RECHERCHE_WEB` : les requêtes envoyées pour la recherche élargie
- `JOURS_RETENTION` : combien de temps un appel reste affiché sur le
  tableau de bord après sa détection (uniquement si sa date de clôture
  réelle est inconnue)
- `VEILLE_CARENEWS_PAGES` (variable d'environnement, 3 par défaut) : nombre
  de pages Carenews parcourues, environ 20 appels par page

### Sélection détaillée Carenews

Pour Carenews, le script ne se contente plus d'un titre : chaque fiche
récupérée inclut désormais :

- le **résumé** complet de l'appel
- l'**organisme financeur** (ex. « Fondation Bouygues Telecom »)
- la **date de publication** et la **date de clôture**

Les appels dont la date de clôture est déjà passée sont automatiquement
écartés — vous ne voyez que ce qui est encore ouvert. Sur le tableau de
bord, l'échéance s'affiche à la place de la date de détection dès qu'elle
est connue, pour prioriser ce qui approche de sa date limite.

Pour élargir la sélection (plus de pages = plus d'ancienneté couverte, au
prix d'un peu plus de temps d'exécution) :

```bash
export VEILLE_CARENEWS_PAGES="5"
```

## 7. Dépannage

- **Carenews ne remonte rien** : la structure HTML du site a pu changer.
  Ouvrez la page dans un navigateur, faites clic droit → « Inspecter » sur
  un titre d'appel à projets, et ajustez le sélecteur dans la fonction
  `collecter_carenews()`.
- **La recherche web ne remonte rien / erreur 202** : DuckDuckGo limite le
  nombre de requêtes automatiques. Espacez les exécutions (une fois par
  semaine suffit largement) ou réduisez `REQUETES_RECHERCHE_WEB`.
- **Aucun email reçu** : vérifiez que les 4 variables `VEILLE_EMAIL_*` sont
  bien définies dans la session qui exécute le script (pas seulement dans
  votre terminal interactif si vous utilisez cron).

## 8. Limites à garder en tête

- Ce script s'appuie en partie sur du *scraping* de pages web publiques : il
  reste soumis aux conditions d'utilisation des sites concernés et peut
  cesser de fonctionner si ces sites changent leur structure. Vérifiez de
  temps en temps que le tableau de bord se met bien à jour.
- Il ne remplace pas une vérification manuelle des dates limites et
  critères d'éligibilité : traitez-le comme un système d'alerte, pas comme
  une source garantie à 100 %.
