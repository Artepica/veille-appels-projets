#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Veille des appels à projets — Art'Epica
=========================================

Cherche automatiquement les appels à projets susceptibles de correspondre
à des projets comme "Regards Connectés" : jeunesse, numérique responsable,
ruralité, art/photographie, citoyenneté, financés par des fondations
bancaires (type Crédit Agricole), des fondations d'entreprise, ou des
plateformes publiques.

Ce script :
  1. Interroge l'API publique Aides-Territoires
  2. Scrape la page "Appels à projets" de Carenews
  3. Fait une recherche web élargie (mots-clés) pour capter les appels
     publiés par des sources plus éparses (caisses locales du Crédit
     Agricole, petites fondations, réseaux associatifs jeunesse/culture)
  4. Dé-duplique par rapport aux résultats déjà vus
  5. Génère un tableau de bord HTML consultable dans un navigateur
  6. Envoie un email récapitulatif des NOUVEAUX appels à projets détectés

À LANCER SOI-MÊME sur son ordinateur / serveur (voir README.md), planifié
par exemple une fois par semaine via cron ou le Planificateur de tâches
Windows. Ce script ne tourne pas "tout seul dans le cloud" : il a besoin
d'être exécuté régulièrement quelque part.
"""

import os
import re
import json
import time
import smtplib
import hashlib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# CONFIGURATION — à adapter à votre projet
# ---------------------------------------------------------------------------

# Mots-clés qui définissent "ce type de projet". Un résultat est retenu s'il
# contient au moins un mot d'un groupe ET (si possible) recoupe un second
# groupe, pour éviter le bruit (voir score_relevance).
MOTS_CLES_THEME = [
    "jeunesse", "jeunes", "adolescents", "lycéens", "enfants", "familles",
    "numérique", "réseaux sociaux", "smartphone", "éducation aux médias",
    "ruralité", "rural", "territoire rural", "monts du lyonnais",
    "photographie", "photo", "art", "artistique", "écriture", "création",
    "citoyen", "citoyenneté", "inclusion", "lien social", "expression",
    "art-thérapie", "médiation artistique", "pouvoir d'agir", "créativité",
    "harcèlement", "anxiété", "burn-out", "santé mentale", "bien-être",
    "isolement", "groupe de parole", "tiers-lieu", "estime de soi",
    "prévention", "accompagnement au changement", "formation",
]

MOTS_CLES_FINANCEURS = [
    "crédit agricole", "caisse locale", "prix coup de cœur", "sociétariat",
    "fondation", "mécénat", "appel à projets", "appel à candidatures",
]

# Requêtes envoyées au moteur de recherche élargi (source 3). Ajustez-les
# librement selon vos priorités.
REQUETES_RECHERCHE_WEB = [
    "appel à projets jeunesse numérique ruralité",
    "appel à projets photographie jeunes",
    "Crédit Agricole caisse locale appel à projets jeunesse",
    "fondation appel à projets éducation aux médias",
    "appel à projets art citoyenneté rural",
    "appel à projets art-thérapie médiation artistique",
    "appel à projets prévention harcèlement scolaire santé mentale jeunes",
    "appel à projets tiers-lieu ruralité innovation",
    "appel à projets isolement lien social groupe de parole",
    "appel à projets outre-mer jeunesse culture association",
]

# Dossier où sont stockés l'historique et le tableau de bord généré
DOSSIER_DONNEES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FICHIER_HISTORIQUE = os.path.join(DOSSIER_DONNEES, "historique.json")
FICHIER_DASHBOARD = os.path.join(DOSSIER_DONNEES, "dashboard.html")

# Dossier "site" : c'est celui qu'on envoie à Netlify (doit contenir un
# index.html à la racine). Le dashboard local (ci-dessus) et la version
# publiée en ligne ont exactement le même contenu.
DOSSIER_SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
FICHIER_SITE_INDEX = os.path.join(DOSSIER_SITE, "index.html")

# Combien de jours un appel à projets reste affiché sur le dashboard après
# sa première détection, UNIQUEMENT si sa date de clôture réelle est
# inconnue (sinon c'est la date de clôture qui fait foi, voir Carenews)
JOURS_RETENTION = 75

# Carenews : nombre de pages parcourues (~20 appels par page)
PAGE_CARENEWS_BASE = "https://www.carenews.com/appels_a_projets"
NB_PAGES_CARENEWS = int(os.environ.get("VEILLE_CARENEWS_PAGES", "3"))

# Email (variables d'environnement — voir README.md, ne mettez jamais de
# mot de passe en clair dans ce fichier)
EMAIL_HOTE = os.environ.get("VEILLE_EMAIL_HOTE", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("VEILLE_EMAIL_PORT", "587"))
EMAIL_UTILISATEUR = os.environ.get("VEILLE_EMAIL_USER")
EMAIL_MOT_DE_PASSE = os.environ.get("VEILLE_EMAIL_PASSWORD")
EMAIL_DESTINATAIRE = os.environ.get("VEILLE_EMAIL_TO")

# Netlify (optionnel — voir README.md § "Mise en ligne sur Netlify")
NETLIFY_TOKEN = os.environ.get("VEILLE_NETLIFY_TOKEN")
NETLIFY_SITE_ID = os.environ.get("VEILLE_NETLIFY_SITE_ID")

ENTETES_HTTP = {
    "User-Agent": "ArtEpica-VeilleAppelsProjets/1.0 (usage associatif non commercial)"
}

# ---------------------------------------------------------------------------
# COLLECTE — Source 1 : API Aides-Territoires
# ---------------------------------------------------------------------------

def collecter_aides_territoires():
    """
    Interroge l'API publique Aides-Territoires.
    Nécessite un token gratuit : voir README.md § "Obtenir un token".
    Sans token, cette source est simplement ignorée (pas d'erreur bloquante).
    """
    token = os.environ.get("VEILLE_AT_TOKEN")
    if not token:
        print("[Aides-Territoires] Pas de token configuré, source ignorée.")
        return []

    resultats = []
    url = "https://aides-territoires.beta.gouv.fr/api/aids/"
    headers = {**ENTETES_HTTP, "Authorization": f"Bearer {token}"}

    for mot in ["jeunesse numérique", "photographie ruralité", "éducation aux médias"]:
        try:
            reponse = requests.get(
                url, headers=headers,
                params={"text": mot, "itemsPerPage": 15},
                timeout=20,
            )
            reponse.raise_for_status()
            donnees = reponse.json()
            for aide in donnees.get("results", []):
                resultats.append({
                    "titre": aide.get("name", "").strip(),
                    "lien": aide.get("url") or aide.get("origin_url") or "",
                    "resume": (aide.get("description") or "")[:300],
                    "source": "Aides-Territoires",
                })
        except requests.RequestException as e:
            print(f"[Aides-Territoires] Erreur sur la requête '{mot}' : {e}")
        time.sleep(1)

    return resultats


# ---------------------------------------------------------------------------
# COLLECTE — Source 2 : Carenews (page "Appels à projets")
# ---------------------------------------------------------------------------

def collecter_carenews():
    """
    Récupère une sélection DÉTAILLÉE des appels à projets publiés sur
    Carenews : titre, lien, résumé, organisme financeur, date de
    publication et date de clôture. Les appels déjà clôturés (date de
    clôture passée) sont automatiquement écartés.

    Carenews liste ~20 appels par page ; NB_PAGES_CARENEWS pages sont
    parcourues (réglable via la variable d'environnement
    VEILLE_CARENEWS_PAGES, 3 par défaut = ~60 appels les plus récents).
    """
    resultats = []
    RE_PUBLICATION = re.compile(r"Publié le\s*:\s*(\d{2}\.\d{2}\.\d{4})")
    RE_CLOTURE = re.compile(r"Date de clôture\s*:\s*(\d{2}\.\d{2}\.\d{4})")
    RE_FINANCEUR = re.compile(r"\bPar\s+([A-ZÉÈÀÂÎÔÛÇ][^\n]{2,70}?)\s*(?:Publié le|$)")

    def parser_date(texte, motif):
        m = motif.search(texte or "")
        if not m:
            return None
        jour, mois, annee = m.group(1).split(".")
        try:
            return datetime.date(int(annee), int(mois), int(jour))
        except ValueError:
            return None

    for page in range(NB_PAGES_CARENEWS):
        url = PAGE_CARENEWS_BASE if page == 0 else f"{PAGE_CARENEWS_BASE}/{page}/"
        try:
            reponse = requests.get(url, headers=ENTETES_HTTP, timeout=20)
            reponse.raise_for_status()
        except requests.RequestException as e:
            print(f"[Carenews] Erreur sur la page {page} : {e}")
            continue

        soupe = BeautifulSoup(reponse.text, "html.parser")
        texte_complet = soupe.get_text("\n", strip=True)

        # Chaque fiche d'appel à projets est un lien dont l'URL contient
        # "/appels-a-projet/". On s'appuie sur ce marqueur plutôt que sur
        # des classes CSS, plus susceptibles de changer avec le temps.
        liens_titres = [
            a for a in soupe.find_all("a", href=True)
            if "/appels-a-projet/" in a["href"] and a.get_text(strip=True)
        ]

        for i, lien_tag in enumerate(liens_titres):
            titre = lien_tag.get_text(strip=True)
            href = lien_tag["href"]
            if not href.startswith("http"):
                href = "https://www.carenews.com" + href

            # Fenêtre de texte entre ce titre et le titre suivant : c'est
            # dans cette zone que se trouvent le résumé, le financeur et
            # les dates de cette fiche précise.
            debut = texte_complet.find(titre)
            fin = len(texte_complet)
            if i + 1 < len(liens_titres):
                position_suivante = texte_complet.find(
                    liens_titres[i + 1].get_text(strip=True), debut + len(titre)
                )
                if position_suivante != -1:
                    fin = position_suivante
            fenetre = texte_complet[debut:fin] if debut != -1 else ""

            date_publication = parser_date(fenetre, RE_PUBLICATION)
            date_cloture = parser_date(fenetre, RE_CLOTURE)

            # Appel déjà clôturé : on l'écarte (marge de prudence conservée
            # pour les dates absentes ou illisibles, à vérifier à la main).
            if date_cloture and date_cloture < datetime.date.today():
                continue

            match_financeur = RE_FINANCEUR.search(fenetre)
            financeur = match_financeur.group(1).strip(" -–") if match_financeur else ""

            # Résumé : le texte entre le titre et le premier marqueur connu
            # ("Par ", "Publié le", "Date de clôture"), nettoyé.
            resume_brut = fenetre[len(titre):]
            for marqueur in ["Publié le", "Date de clôture", "\nPar "]:
                position = resume_brut.find(marqueur)
                if position != -1:
                    resume_brut = resume_brut[:position]
            resume = resume_brut.strip(" \n-")[:400]

            resultats.append({
                "titre": titre,
                "lien": href,
                "resume": resume,
                "financeur": financeur,
                "date_publication": date_publication.isoformat() if date_publication else "",
                "date_cloture": date_cloture.isoformat() if date_cloture else "",
                "source": "Carenews",
            })

        time.sleep(1.5)  # on reste courtois avec le serveur de Carenews

    print(f"[Carenews] {len(resultats)} appels à projets récupérés en détail sur {NB_PAGES_CARENEWS} page(s).")
    return resultats


# ---------------------------------------------------------------------------
# COLLECTE — Source 3 : recherche web élargie (DuckDuckGo HTML)
# ---------------------------------------------------------------------------

def collecter_recherche_web():
    """
    Recherche élargie pour capter les sources trop dispersées pour être
    listées une par une (caisses locales du Crédit Agricole, petites
    fondations, réseaux associatifs jeunesse/culture...).
    Utilise la version HTML de DuckDuckGo, qui ne nécessite pas de clé API.
    """
    resultats = []
    for requete in REQUETES_RECHERCHE_WEB:
        try:
            reponse = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": requete},
                headers=ENTETES_HTTP,
                timeout=20,
            )
            reponse.raise_for_status()
            soupe = BeautifulSoup(reponse.text, "html.parser")
            for bloc in soupe.select(".result__body")[:10]:
                lien_tag = bloc.select_one("a.result__a")
                snippet_tag = bloc.select_one(".result__snippet")
                if not lien_tag:
                    continue
                resultats.append({
                    "titre": lien_tag.get_text(strip=True),
                    "lien": lien_tag.get("href", ""),
                    "resume": snippet_tag.get_text(strip=True) if snippet_tag else "",
                    "source": f"Recherche web ({requete})",
                })
        except requests.RequestException as e:
            print(f"[Recherche web] Erreur sur '{requete}' : {e}")
        time.sleep(2)  # on reste courtois avec le moteur de recherche

    return resultats


# ---------------------------------------------------------------------------
# FILTRAGE / SCORE DE PERTINENCE
# ---------------------------------------------------------------------------

def score_pertinence(item):
    """
    Score simple : +1 par mot-clé thématique trouvé, +1 par mot-clé
    financeur trouvé, dans le titre + résumé + financeur. Permet de trier
    par pertinence et d'écarter le bruit de la recherche web élargie.
    """
    texte = f"{item['titre']} {item['resume']} {item.get('financeur', '')}".lower()
    score = 0
    for mot in MOTS_CLES_THEME:
        if mot in texte:
            score += 1
    for mot in MOTS_CLES_FINANCEURS:
        if mot in texte:
            score += 1
    return score


# Seuil minimum de pertinence par source. Carenews ne liste déjà que des
# appels à projets réels (source pré-qualifiée) : on garde tout et on se
# sert du score seulement pour le tri/affichage. Les sources plus bruitées
# (recherche web élargie) sont filtrées plus strictement.
SEUILS_PAR_SOURCE = {
    "Carenews": 0,
    "Aides-Territoires": 0,
}
SEUIL_PAR_DEFAUT = 1


def filtrer_et_scorer(items):
    vus = set()
    retenus = []
    for item in items:
        lien = item.get("lien", "").split("?")[0].rstrip("/")
        if not lien or lien in vus:
            continue
        vus.add(lien)
        item["score"] = score_pertinence(item)
        seuil = SEUILS_PAR_SOURCE.get(item.get("source"), SEUIL_PAR_DEFAUT)
        if item["score"] >= seuil:
            retenus.append(item)
    retenus.sort(key=lambda x: x["score"], reverse=True)
    return retenus


# ---------------------------------------------------------------------------
# HISTORIQUE / DÉDUPLICATION
# ---------------------------------------------------------------------------

def cle_item(item):
    return hashlib.sha256(item["lien"].encode("utf-8")).hexdigest()


def charger_historique():
    if os.path.exists(FICHIER_HISTORIQUE):
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def sauvegarder_historique(historique):
    os.makedirs(DOSSIER_DONNEES, exist_ok=True)
    with open(FICHIER_HISTORIQUE, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=2)


def mettre_a_jour_historique(items_retenus, historique):
    """Retourne (nouveaux, tous_les_actifs) et met à jour l'historique en place."""
    aujourdhui = datetime.date.today().isoformat()
    nouveaux = []

    for item in items_retenus:
        cle = cle_item(item)
        if cle not in historique:
            item["premiere_detection"] = aujourdhui
            historique[cle] = item
            nouveaux.append(item)
        else:
            # on garde la date de première détection d'origine
            historique[cle]["score"] = max(historique[cle].get("score", 0), item["score"])

    # Purge : priorité à la vraie date de clôture quand elle est connue
    # (ex. Carenews), sinon on retombe sur JOURS_RETENTION depuis la
    # première détection.
    aujourdhui_date = datetime.date.today()
    limite_detection = aujourdhui_date - datetime.timedelta(days=JOURS_RETENTION)
    a_supprimer = []
    for cle, val in historique.items():
        date_cloture = val.get("date_cloture")
        if date_cloture:
            expire = datetime.date.fromisoformat(date_cloture) < aujourdhui_date
        else:
            expire = datetime.date.fromisoformat(val["premiere_detection"]) < limite_detection
        if expire:
            a_supprimer.append(cle)
    for cle in a_supprimer:
        del historique[cle]

    tous_les_actifs = sorted(
        historique.values(), key=lambda x: x["premiere_detection"], reverse=True
    )
    return nouveaux, tous_les_actifs


# ---------------------------------------------------------------------------
# TABLEAU DE BORD HTML
# ---------------------------------------------------------------------------

def generer_dashboard(items_actifs, chemin_sortie=FICHIER_DASHBOARD):
    os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
    date_generation = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")

    def fmt_date(iso):
        if not iso:
            return ""
        return datetime.date.fromisoformat(iso).strftime("%d/%m/%Y")

    cartes_html = ""
    for item in items_actifs:
        titre = item["titre"].replace("<", "&lt;")
        resume = (item.get("resume") or "").replace("<", "&lt;")
        source = item.get("source", "")
        lien = item.get("lien", "#")
        financeur = (item.get("financeur") or "").replace("<", "&lt;")
        date_cloture = fmt_date(item.get("date_cloture", ""))
        date_detection = item.get("premiere_detection", "")

        meta_droite = f"échéance : {date_cloture}" if date_cloture else f"détecté le {date_detection}"
        ligne_financeur = f'<p class="financeur">{financeur}</p>' if financeur else ""

        cartes_html += f"""
        <article class="carte">
          <div class="carte-entete">
            <span class="source">{source}</span>
            <span class="date">{meta_droite}</span>
          </div>
          <h2><a href="{lien}" target="_blank" rel="noopener">{titre}</a></h2>
          {ligne_financeur}
          <p class="resume">{resume}</p>
        </article>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Veille des appels à projets — Art'Epica</title>
<style>
  :root {{
    --papier: #F6F4EE;
    --encre: #23261F;
    --sauge: #556B4F;
    --sepia: #A87B4B;
    --filet: #DAD4C4;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--papier);
    color: var(--encre);
    font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
    line-height: 1.5;
  }}
  header {{
    padding: 3.5rem 1.5rem 2rem;
    max-width: 760px;
    margin: 0 auto;
    border-bottom: 1px solid var(--filet);
  }}
  header .eyebrow {{
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 0.8rem;
    color: var(--sauge);
    letter-spacing: 0.02em;
    margin: 0 0 0.4rem;
  }}
  header h1 {{
    font-size: 2.1rem;
    margin: 0 0 0.6rem;
    font-weight: 500;
  }}
  header p {{
    font-family: -apple-system, "Segoe UI", sans-serif;
    color: #55584f;
    font-size: 0.95rem;
    max-width: 60ch;
  }}
  main {{
    max-width: 760px;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
  }}
  .carte {{
    padding: 1.4rem 0;
    border-bottom: 1px solid var(--filet);
  }}
  .carte-entete {{
    display: flex;
    justify-content: space-between;
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 0.78rem;
    color: var(--sepia);
    margin-bottom: 0.35rem;
  }}
  .carte h2 {{
    font-size: 1.2rem;
    font-weight: 500;
    margin: 0 0 0.4rem;
  }}
  .carte h2 a {{
    color: var(--encre);
    text-decoration: none;
    border-bottom: 1px solid var(--sauge);
  }}
  .carte h2 a:hover {{
    color: var(--sauge);
  }}
  .financeur {{
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 0.85rem;
    color: var(--sauge);
    margin: 0 0 0.3rem;
    font-weight: 600;
  }}
  .resume {{
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 0.92rem;
    color: #4a4d42;
    margin: 0;
  }}
  footer {{
    max-width: 760px;
    margin: 0 auto;
    padding: 1rem 1.5rem 3rem;
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 0.78rem;
    color: #8a8d80;
  }}
</style>
</head>
<body>
<header>
  <p class="eyebrow">Art'Epica · Veille</p>
  <h1>Appels à projets à surveiller</h1>
  <p>Jeunesse, numérique responsable, ruralité, art et photographie. Généré automatiquement le {date_generation} — {len(items_actifs)} appel(s) actif(s).</p>
</header>
<main>
{cartes_html if cartes_html else "<p>Aucun appel à projets actif pour le moment.</p>"}
</main>
<footer>
  Généré automatiquement à partir d'Aides-Territoires, Carenews et d'une recherche web élargie.
  Vérifiez toujours les dates et conditions directement auprès de l'organisme avant de candidater.
</footer>
</body>
</html>"""

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        f.write(html)

    # Copie identique dans le dossier "site" (celui publié sur Netlify)
    os.makedirs(DOSSIER_SITE, exist_ok=True)
    with open(FICHIER_SITE_INDEX, "w", encoding="utf-8") as f:
        f.write(html)

    # Netlify a un bug connu : un zip de déploiement contenant UN SEUL
    # fichier est parfois mal traité et servi en texte brut au lieu de
    # HTML (voir forum Netlify). On ajoute donc systématiquement un
    # second petit fichier, inoffensif, pour éviter ce cas de figure.
    with open(os.path.join(DOSSIER_SITE, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\n")

    return chemin_sortie


# ---------------------------------------------------------------------------
# EMAIL RÉCAPITULATIF
# ---------------------------------------------------------------------------

def envoyer_email(nouveaux, chemin_dashboard):
    if not (EMAIL_UTILISATEUR and EMAIL_MOT_DE_PASSE and EMAIL_DESTINATAIRE):
        print("[Email] Configuration incomplète (variables VEILLE_EMAIL_*), envoi ignoré.")
        return

    if not nouveaux:
        print("[Email] Aucun nouvel appel à projets, pas d'email envoyé.")
        return

    corps = "Nouveaux appels à projets détectés :\n\n"
    for item in nouveaux:
        corps += f"- {item['titre']} ({item['source']})\n  {item['lien']}\n\n"
    corps += f"\nTableau de bord complet : {chemin_dashboard}\n"

    message = MIMEMultipart()
    message["From"] = EMAIL_UTILISATEUR
    message["To"] = EMAIL_DESTINATAIRE
    message["Subject"] = f"Veille appels à projets — {len(nouveaux)} nouveauté(s)"
    message.attach(MIMEText(corps, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_HOTE, EMAIL_PORT) as serveur:
            serveur.starttls()
            serveur.login(EMAIL_UTILISATEUR, EMAIL_MOT_DE_PASSE)
            serveur.send_message(message)
        print(f"[Email] Envoyé à {EMAIL_DESTINATAIRE} ({len(nouveaux)} nouveauté(s)).")
    except smtplib.SMTPException as e:
        print(f"[Email] Erreur d'envoi : {e}")


# ---------------------------------------------------------------------------
# MISE EN LIGNE SUR NETLIFY (optionnel)
# ---------------------------------------------------------------------------

def deployer_netlify():
    """
    Publie le contenu de DOSSIER_SITE sur Netlify via leur API de déploiement
    ("zip deploy"), sans dépendance à Node.js ni à la CLI Netlify.
    Nécessite VEILLE_NETLIFY_TOKEN et VEILLE_NETLIFY_SITE_ID (voir README.md).
    Ignoré silencieusement (avec un message) si non configuré.
    """
    if not (NETLIFY_TOKEN and NETLIFY_SITE_ID):
        print("[Netlify] Non configuré (VEILLE_NETLIFY_TOKEN / VEILLE_NETLIFY_SITE_ID absents), publication ignorée.")
        return

    import zipfile
    import io

    tampon_zip = io.BytesIO()
    with zipfile.ZipFile(tampon_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for racine, _dossiers, fichiers in os.walk(DOSSIER_SITE):
            for nom_fichier in fichiers:
                chemin_complet = os.path.join(racine, nom_fichier)
                chemin_relatif = os.path.relpath(chemin_complet, DOSSIER_SITE)
                archive.write(chemin_complet, chemin_relatif)
    tampon_zip.seek(0)

    url = f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys"
    headers = {
        "Authorization": f"Bearer {NETLIFY_TOKEN}",
        "Content-Type": "application/zip",
    }

    try:
        reponse = requests.post(url, headers=headers, data=tampon_zip.getvalue(), timeout=60)
        reponse.raise_for_status()
        donnees = reponse.json()
        url_site = donnees.get("ssl_url") or donnees.get("url") or "(url non retournée)"
        print(f"[Netlify] Publié avec succès : {url_site}")
    except requests.RequestException as e:
        print(f"[Netlify] Erreur de publication : {e}")


# ---------------------------------------------------------------------------
# ORCHESTRATION
# ---------------------------------------------------------------------------

def main():
    print("=== Veille des appels à projets — Art'Epica ===")

    bruts = []
    bruts += collecter_aides_territoires()
    bruts += collecter_carenews()
    bruts += collecter_recherche_web()
    print(f"Total brut collecté : {len(bruts)}")

    retenus = filtrer_et_scorer(bruts)
    print(f"Retenus après filtrage par pertinence : {len(retenus)}")

    historique = charger_historique()
    nouveaux, actifs = mettre_a_jour_historique(retenus, historique)
    sauvegarder_historique(historique)
    print(f"Nouveaux depuis la dernière exécution : {len(nouveaux)}")

    chemin = generer_dashboard(actifs)
    print(f"Tableau de bord généré : {chemin}")

    deployer_netlify()
    envoyer_email(nouveaux, chemin)


if __name__ == "__main__":
    main()
