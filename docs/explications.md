# ScholarFund AI — État du prototype

> Prototype éducatif. Les résultats ne sont pas un conseil financier.

## En bref

ScholarFund AI aide un fonds de bourses d'études, sur le modèle de
Harvard, à choisir comment placer son capital. Le client choisit un
scénario (prudence, éthique, part de private equity, taxe d'accise,
inflation, montant de la bourse) ; le prototype :

1. récupère des données publiques (prix des ETF, inflation, données
   éthiques sur les entreprises) ;
2. simule trois stratégies d'investissement et teste si elles peuvent
   payer les bourses pendant 10 ans (horizon réglable), y compris après
   un krach ;
3. recommande une stratégie, ou explique qu'aucune ne passe et quelle
   bourse serait tenable ;
4. fait expliquer le résultat en langage clair par un LLM (Azure OpenAI),
   qui n'a le droit d'utiliser que les chiffres du modèle ;
5. affiche tout cela dans la webapp Streamlit (`app.py`), où le client
   règle son scénario et peut discuter avec l'analyste IA.

**Deux sujets propres à Harvard** sont modélisés :

- **la taxe d'accise 2026 à paliers** (1,4 / 4 / 8 % ; Harvard est à
  8 %), payée sur les plus-values réalisées quand le fonds vend ;
- **la liquidité du private equity** : Harvard en détient plus de 40 %,
  ce qui l'a mis en difficulté ; le modèle vise 20 %, et montre ce que 40 %
  changerait.

**Résultat principal** (données d'octobre 2026, réglages par défaut :
100 000 $, Balanced, filtre Moderate, 20 % de private equity, taxe de
2 %, versement de 4 %, inflation de 3 %, 10 ans) : Balanced est
recommandée. Avec 6 % de versement et un krach, un fonds à 40 % de
private equity manque des bourses dans 9,4 % des cas parce que l'argent
est bloqué, contre 0 % à 20 %.

---

## 1. Démarrer

**Installation**

```bash
pip install -r requirements.txt
```

**Clés d'API** : copier `.env.example` en `.env` et remplir les clés. Le
fichier `.env` est exclu de git ; ne jamais mettre de clé dans le code ni
dans `.env.example`.

| Variable | Utilisation |
|---|---|
| `FRED_API_KEY` | inflation et taux des T-bills |
| `FINNHUB_API_KEY` | cours et actualités (pas encore utilisé par le modèle) |
| `WIKIRATE_API_KEY` | données éthiques sur les entreprises |
| `AZURE_OPENAI_API_KEY` | explication par le LLM |

Le point d'accès Azure, le modèle (`gpt-6.1-sol`) et la version d'API
reprennent ceux de `templates/main.py` ; ils peuvent être changés dans `.env`.

**Commandes utiles**

| Commande | Ce qu'elle fait |
|---|---|
| `python -m pytest` | 61 tests hors ligne, sans clé |
| `python -m scholarfund.check_connections` | vérifie chaque source de données |
| `python -m scholarfund.analysis` | analyse chiffrée sur données réelles |
| `python -m scholarfund.llm_explainer` | explication par le LLM, enregistrée dans `reports/` |
| `streamlit run app.py` | **lance la webapp** (http://localhost:8501) |

Toutes les commandes se lancent depuis la racine du projet.

---

## 2. Vue d'ensemble

```
Yahoo Finance ─┐
FRED ──────────┼─> analysis.py ─> finance.py (simulation, tests,
Wikirate ──────┘   (+ ethics.py)    recommandation)
                                        │
                                        ├─> llm_explainer.py ─> Azure OpenAI
                                        │
webapp Streamlit : app.py <── model.py (adaptateur) + llm.py (chat)
```

- `analysis.run_analysis(...)` lance toute la chaîne pour un scénario et
  renvoie un seul dictionnaire : résultats et contexte des données.
- Les données du marché et de FRED sont gardées en mémoire pour la
  journée ; le filtre éthique est mis en cache dans `.cache/`.

---

## 3. Données

### Prix des ETF (Yahoo Finance, `market_data.py`)

| ETF | Contenu | Classe dans le modèle |
|---|---|---|
| BIL | bons du Trésor américain à 1-3 mois | obligations et bons du Trésor |
| BND | obligations américaines (État et entreprises) | obligations et bons du Trésor |
| BNDX | obligations internationales, couvertes contre le risque de change | obligations et bons du Trésor |
| VTI | actions américaines | actions |
| VXUS | actions internationales hors États-Unis | actions |
| ESGV | actions américaines, version ESG (remplace VTI si VTI est exclu) | actions |
| VSGX | actions internationales, version ESG (remplace VXUS si VXUS est exclu) | actions |

- Seuls les cours de clôture journaliers ajustés (dividendes inclus) sont
  utilisés, convertis en rendements mensuels.
- Historique : **juin 2007 à septembre 2026 (232 mois)**, crise de 2008
  comprise. Le mois en cours, incomplet, est exclu.
- VXUS n'existe que depuis 2011 : avant, ses rendements sont remplacés
  par ceux de VEU, un fonds très proche (corrélation mensuelle de 0,998).
- BNDX n'existe que depuis 2013 : avant, ses rendements sont remplacés
  par ceux de BND (corrélation de 0,86, volatilité proche), plus proche
  que les fonds d'obligations internationales non couverts.
- ESGV et VSGX n'existent que depuis 2018 : avant, leurs rendements sont
  remplacés par ceux de VTI et VXUS (corrélation de 0,994).
- Ces remplacements de données sont indiqués dans les résultats.
- Le private equity n'a pas de données de marché : c'est une hypothèse
  (section 5).
- « Moins risqué » est une simplification : les obligations peuvent
  aussi perdre de la valeur.

### Inflation et taux (FRED, `fred_data.py`)

- Hypothèse d'inflation par défaut : inflation CPI moyenne sur 10 ans,
  **3,41 %** en octobre 2026. Si FRED ne répond pas, le modèle utilise
  3 % et le signale. Le client peut aussi choisir sa propre valeur.
- Le taux des T-bills à 3 mois est affiché pour information.

### Données éthiques (Wikirate, `wikirate_data.py`)

Données ouvertes et communautaires sur les entreprises. Utilisées par le
filtre éthique (section 6).

### Finnhub (`finnhub_data.py`)

Connecté (cours, profils d'entreprise, actualités d'une semaine au plus
en version gratuite) mais pas encore utilisé par le modèle. Les avoirs
des ETF et les scores ESG sont payants : le code s'arrête avec une erreur
claire plutôt que d'inventer des données.

---

## 4. Le scénario du client

| Paramètre | Valeurs | Défaut (moteur) | Défaut (webapp) |
|---|---|---|---|
| Prudence (`risk_tolerance`) | Conservative, Balanced, Growth | Balanced | Balanced |
| Éthique (`ethical_policy`) | Standard, Moderate, Strict | Standard | Moderate |
| Private equity (`pe_share`) | part du fonds ; webapp : 0, 20 % (cible) ou 40 % (Harvard aujourd'hui) | 20 % | 20 % |
| Taxe d'accise (`excise_tax_rate`) | taux sur les plus-values réalisées ; webapp : interrupteur + taux | 0 | activée, 2 % |
| Bourse annuelle (`annual_payout`) | en $, indexée chaque année sur l'inflation ; webapp : % du don | 5 000 $ | 4 % |
| Inflation (`inflation_rate`) | décimal (0,03 = 3 %) | moyenne FRED | 3 % |
| Capital (`initial_capital`) | en $ | 100 000 $ | 100 000 $ |
| Horizon (`horizon_years`) | durée des simulations, en années | 10 | 10 |

---

## 5. Allocation, réserve et règles de prélèvement

### Structure du fonds

```
Fonds = private equity (20 %)  +  marchés publics (80 %)
                                   ├─ obligations et bons du Trésor (réserve comprise)
                                   └─ actions
```

**Marchés publics** : chaque classe pèse toujours **au moins 30 %** ; les
40 % restants vont à l'une ou à l'autre selon le profil.

| Profil | Obligations et bons du Trésor | Actions |
|---|---|---|
| Conservative | 70 % | 30 % |
| Balanced | 50 % | 50 % |
| Growth | 30 % | 70 % |

À l'intérieur de chaque classe (surtout américain, avec un peu de
diversification internationale) :

| Classe | Répartition |
|---|---|
| Obligations et bons du Trésor | bons du Trésor US 15 % (BIL), obligations US 65 % (BND), obligations internationales 20 % (BNDX) |
| Actions | actions US 65 % (VTI, sinon ESGV), actions internationales 35 % (VXUS, sinon VSGX) |

- La **réserve** de bourses fait partie de la classe obligations et bons
  du Trésor (elle est en BIL).
- Chaque classe est découpée en **zones** (US / international). Si le
  filtre éthique exclut le fonds d'une zone, il est **remplacé par sa
  version ESG** de la même zone : l'argent reste réparti entre zones au
  lieu de s'empiler dans un seul fonds. L'app affiche chaque remplacement.
- Si une zone n'a aucun fonds autorisé, son poids va aux autres zones de
  la classe (c'est signalé). Si toute une classe est vide, la stratégie
  est indisponible (la règle des 30 % ne peut pas être tenue).
- Le client ne voit que les stratégies **pas plus risquées que son
  profil**.

Exemple, Balanced avec le filtre Moderate (VXUS exclu, remplacé par
VSGX), 100 000 $ : 20 000 $ de private equity ; 12 902 $ en BIL (réserve
comprise), 20 722 $ en BND, 6 376 $ en BNDX ; 26 000 $ en VTI et 14 000 $
en VSGX.

### Private equity (hypothèse illustrative)

- **Pourquoi** : Harvard détient plus de 40 % de son fonds en private
  equity, ce qui a créé des problèmes de liquidité ; l'objectif est de
  revenir à 20 %.
- **Hypothèses** : rendement fixe de **9 % par an** (en dessous des 11-13 %
  des 15 dernières années, donc prudent), capital **bloqué 7 ans** : il ne
  peut ni payer les bourses ni remplir la réserve avant. Ensuite, il peut
  être vendu en dernier recours. Dans le scénario de krach, il perd 30 %.
- **Ce qui est mesuré** : la part du fonds en private equity au fil du
  temps (elle augmente quand les actifs publics paient les bourses : c'est
  l'« effet dénominateur »), et la part des simulations où une bourse est
  manquée alors que l'argent existait mais était bloqué.
- **Limite** : un rendement fixe rend le private equity lisse et
  attrayant ; le vrai private equity est plus risqué. Les rendements et
  volatilités affichés pour les stratégies portent sur les marchés publics
  seuls ; « With PE » ajoute le rendement supposé du private equity.

### Taxe d'accise (modélisée sur la taxe 2026 à paliers)

- Depuis 2026, la taxe d'accise des universités américaines dépend de la
  dotation par étudiant : **1,4 %, 4 % ou 8 %**. Harvard est au palier de
  8 % (contre 1,4 % avant).
- Dans le modèle, elle est payée sur la **plus-value réalisée** chaque fois
  que le fonds vend un actif qui a pris de la valeur (pour payer une
  bourse, remplir la réserve ou rééquilibrer). Le fonds vend donc un peu
  plus pour couvrir la taxe. Le coût d'achat de chaque poche est suivi
  pour calculer la plus-value.
- Simplification : la vraie taxe porte aussi sur les dividendes et les
  intérêts.

### Poches et règles de prélèvement

Le fonds est réparti en quatre poches : **cash** (la réserve, en BIL),
**moins risquée** (les autres obligations et bons du Trésor),
**croissance** (actions) et **private equity**. Chaque mois :

1. chaque poche reçoit son rendement ;
2. la bourse est payée par la poche cash ; si elle est vide, par la poche
   moins risquée, puis par les actions, puis par le private equity s'il
   n'est plus bloqué ;
3. la poche cash est remplie à nouveau pour couvrir les 24 prochains
   versements : d'abord par les actions, sauf si elles sont en baisse,
   puis par la poche moins risquée, puis par le private equity débloqué ;
4. une fois par an, poche moins risquée et actions sont ramenées à leur
   répartition cible, sauf si les actions sont en baisse. Le private
   equity n'est jamais rééquilibré.

« En baisse » veut dire **plus de 10 % sous leur dernier plus haut** : les
actions ne sont alors pas vendues, sauf s'il ne reste rien d'autre (vente
forcée, comptée). Chaque vente d'un actif en plus-value paie la taxe
d'accise.

---

## 6. Filtre éthique (`ethics.py`, preuve de concept)

Construit uniquement avec des données gratuites.

**Ce qui est examiné**

- **Fonds actions (VTI, VXUS)** : leurs 10 principales positions publiées
  par Yahoo, soit environ 35 % de VTI et 15 % de VXUS. Pour chaque
  entreprise : son secteur (Yahoo) et son engagement public en matière de
  droits humains (Wikirate, World Benchmarking Alliance). L'engagement
  climat (SBTi 1,5 °C) est affiché pour information seulement.
- **Fonds obligataires (BIL, BND, BNDX)** : leurs avoirs ne sont pas
  disponibles gratuitement ; ils sont jugés sur leur part de dette
  publique américaine.

**Règles**

| Politique | Fonds actions | Fonds obligataires |
|---|---|---|
| Standard | pas de filtre | pas de filtre |
| Moderate | exclu si une des principales positions relève des énergies fossiles, du tabac ou de l'armement | acceptés, sans examen par entreprise |
| Strict | Moderate + aucune entreprise sans engagement droits humains, et au moins 80 % du poids examiné avec un engagement vérifié | au moins 90 % de dette publique américaine |

Une réponse absente sur Wikirate ne compte **jamais** comme validée.

**Résultat actuel**

| ETF | Moderate | Strict |
|---|---|---|
| BIL | accepté | accepté (99,8 % de dette publique) |
| BND | accepté | exclu (52 % de dette publique) |
| BNDX | accepté | exclu (78 % de dette publique selon Yahoo) |
| VTI | accepté | exclu (Alphabet sans engagement droits humains) |
| VXUS | exclu (Shell, secteur Énergie) | exclu |
| ESGV | accepté | exclu (Alphabet sans engagement droits humains) |
| VSGX | accepté | exclu (Alibaba, AstraZeneca sans engagement ; trop peu de réponses vérifiées) |

En Strict, aucune action n'est acceptée : toutes les stratégies sont
indisponibles, puisque la règle des 30 % d'actions ne peut pas être tenue.

**Limites** : seule une petite partie de chaque fonds est examinée ; les
noms d'entreprises de Yahoo et de Wikirate ne correspondent pas toujours
(« non trouvé » = non validé) ; Wikirate peut être incomplet.

---

## 7. Simulations et tests de financement

Chaque stratégie disponible est simulée trois fois.

1. **Historique** : les 232 mois réels, avec les règles de la section 5
   (sur toute la période, pas seulement sur l'horizon).
2. **Long terme (Monte Carlo)** : 1 000 trajectoires de 10 ans (horizon
   réglable), construites
   en tirant au hasard des blocs de 12 mois consécutifs de l'historique.
   Les mêmes tirages servent pour toutes les stratégies, et une graine
   fixe rend les résultats reproductibles.
3. **Stress** : les mêmes trajectoires, avec un krach le premier mois :
   BIL 0 %, BND et BNDX -10 %, actions -40 %, private equity -30 %. Avec
   20 % de private equity et le filtre Moderate, le choc total est
   d'environ -20 % pour Conservative, -25 % pour Balanced et -30 % pour
   Growth.

**Pour passer, une stratégie doit :**

- payer toutes les bourses sur l'historique ;
- payer toutes les bourses dans au moins **90 %** des trajectoires
  long terme ;
- faire de même dans le scénario de stress.

Indicateurs calculés : rendement annualisé, volatilité et baisse
maximale (marchés publics), rendement avec private equity, taux de
réussite, part des trajectoires avec une vente forcée, soldes finaux
(5e, 50e et 95e percentiles), taxe d'accise payée, part maximale du
private equity, bourses manquées à cause de l'argent bloqué, et
**préservation de la valeur réelle** : part des trajectoires qui
finissent avec au moins le capital de départ en dollars d'aujourd'hui.
Ce dernier indicateur est affiché mais ne sert pas de test. Ce sont des
mesures du passé, pas des prévisions.

---

## 8. Recommandation

- On recommande la stratégie qui **correspond au profil du client** si
  elle passe tous les tests ; sinon, **la moins risquée suivante** qui
  passe.
- Une stratégie qui rate un test est écartée, pas pénalisée. Le résultat
  indique pour chaque stratégie les tests ratés, et donne la raison de la
  recommandation.
- Si aucune stratégie ne passe, aucune recommandation n'est forcée. Le
  modèle calcule alors la **bourse tenable** : pour chaque stratégie, la
  bourse annuelle la plus élevée qui passerait tous les tests (à 50 $
  près).

Formulation honnête : « la stratégie a passé les scénarios testés », pas
« les bourses sont garanties ».

---

## 9. Explication par le LLM (`llm_explainer.py`)

**Ce que reçoit le LLM** : une version compacte de l'analyse : scénario,
recommandation et raison, bourses tenables, allocation en dollars,
indicateurs et tests ratés par stratégie (dont taxe payée et liquidité
du private equity), règles du modèle, sources et dates des données,
résumé du filtre éthique, avertissement.

**Ce que le prompt lui impose**

- utiliser uniquement ces faits et chiffres, sans rien inventer ;
- ne jamais parler de garantie ;
- dire d'abord s'il n'y a pas de recommandation ;
- expliquer chaque règle qui a joué et citer les limites des données ;
- présenter la taxe comme « modeled on the new 2026 tiered endowment
  excise tax », avec son palier et son coût (ou dire qu'elle est
  désactivée) ;
- présenter le private equity comme une hypothèse illustrative liée à la
  situation de Harvard (plus de 40 %, cible de 20 %), avec la hausse de sa
  part et les bourses manquées à cause de l'argent bloqué ;
- ne donner aucun conseil d'achat, et finir par l'avertissement ;
- suivre un plan fixe : recommandation, pourquoi, risques et stress,
  taxe d'accise, private equity et liquidité, filtre éthique, ce qui
  changerait le résultat, limites.

La langue de l'explication est un paramètre (anglais, français…).

**Contrôle des chiffres** : `unverified_numbers()` liste les nombres du
texte qui ne correspondent à aucune donnée envoyée (formats anglais et
français compris). C'est un filet de sécurité, pas une preuve : il
signale aussi les calculs faits par le LLM (par exemple 5 000 - 3 900 =
1 100 $), qu'il faut alors vérifier à la main.

---

## 10. Webapp Streamlit (`app.py`, `model.py`, `llm.py`)

La webapp de l'équipe garde son interface et son style ; ses calculs
passent maintenant par notre moteur.

- **`model.py`** est un adaptateur : il traduit les réglages de l'app en
  scénario pour le moteur (taux de versement en % → bourse en $, inflation,
  taxe et private equity en % → décimal) et lance trois analyses : le
  scénario choisi, le même sans taxe (ou avec la taxe de 8 % si elle est
  désactivée), et le même avec l'autre part de private equity (40 % si on
  est à 20 % ou 0, sinon 20 %). Les faits Harvard (`HARVARD`) sont repris
  tels quels, à vérifier.
- **`llm.py`** garde le chat de l'équipe : l'analyste répond à partir des
  résultats du moteur et peut **modifier les réglages** en terminant sa
  réponse par une ligne `ACTION: {...}`, dont les valeurs sont bornées
  avant d'être appliquées. Il utilise la même connexion Azure que
  `llm_explainer.py`.
- **`app.py`** : barre latérale (prudence, éthique en trois niveaux,
  private equity 0 / 20 / 40 %, don, taux de versement, interrupteur et
  taux de la taxe d'accise, horizon, inflation),
  puis :

| Onglet | Contenu |
|---|---|
| Allocation | montant par classe d'actifs (réserve et private equity compris), tests ratés |
| Simulation | stratégies comparées (dont taxe payée), bourse tenable, valeur du fonds depuis 2007 |
| Liquidity | private equity choisi contre l'autre niveau : part maximale du PE, bourses manquées à cause de l'argent bloqué, part du PE au fil du temps |
| Endowment tax | taxe choisie contre sans taxe (ou 8 %) : taxe payée, valeur finale, valeur réelle |
| Ethics | résultat du filtre par ETF, entreprises examinées |
| AI analyst | mémo pour le comité, explication complète avec contrôle des chiffres, chat |
| Data & assumptions | sources, dates, règles, rendements des 12 derniers mois |

- En haut : une bannière verte (stratégie recommandée) ou orange (aucune
  ne passe, avec la bourse tenable), et cinq indicateurs clés.
- Le thème clair et la couleur cramoisie sont fixés dans
  `.streamlit/config.toml`, pour que le style de l'équipe s'affiche aussi
  sur un navigateur en mode sombre.
- Chaque scénario prend une à quelques secondes la première fois, puis
  est gardé en mémoire.

Réglages par défaut : Balanced, filtre Moderate, 20 % de private equity,
taxe activée à 2 %, versement de 4 %, inflation de 3 % (la moyenne FRED
sur 10 ans, 3,4 %, est indiquée à côté du curseur), 10 ans. Avec ces
réglages, Balanced est recommandée.

Exemple de démo (liquidité) : monter le versement à 6 %, puis passer le
private equity à 40 % (« Harvard today »). Dans l'onglet Liquidity, la
part du private equity grimpe jusqu'à environ 83 % du fonds, et après un
krach, 9,4 % des simulations manquent une bourse parce que l'argent est
bloqué, contre 0 % à 20 %. À 7 % de versement, l'écart passe à 28,1 %
contre 1,7 %.

### Mode d'emploi

1. **Lancer** : `streamlit run app.py`, puis ouvrir http://localhost:8501.
   Le premier calcul prend quelques secondes (téléchargement des données
   du jour).
2. **Régler le scénario** dans la barre de gauche : prudence, filtre
   éthique, private equity, montant du don, taux de versement, taxe
   d'accise, horizon, inflation. Tout se recalcule à chaque changement.
3. **Lire le verdict** en haut : bannière verte = stratégie recommandée ;
   bannière orange = aucune stratégie ne passe, avec la bourse tenable.
   Les cinq cartes donnent la stratégie affichée, ses taux de réussite
   (normal et après un krach), la chance de garder la valeur réelle du
   don, et le total des bourses à verser sur l'horizon.
4. **Explorer les onglets** pour le détail : allocation en dollars,
   comparaison des stratégies, liquidité du private equity, effet de la
   taxe, filtre éthique, sources.
5. **Utiliser l'analyste IA** (onglet « AI analyst ») : mémo pour le
   comité, explication complète avec contrôle des chiffres, ou chat. Dans
   le chat, on peut demander de changer un réglage (« baisse le versement
   à 3,5 % ») : l'analyste l'applique et les résultats se mettent à jour.

## 11. Résultats actuels (octobre 2026)

**Réglages par défaut de l'app, client Growth** (Moderate, 20 % de
private equity, taxe de 2 %, versement de 4 %, inflation de 3 %, 10 ans)

| Stratégie | Obligations / actions (marchés publics) | Pire baisse (2007-2026) | Après un krach | Garde la valeur réelle | Part max. du PE | Taxe payée (médiane) |
|---|---|---|---|---|---|---|
| Conservative | 70 / 30 | -16 % | 100 % | 13,7 % | 41 % | 324 $ |
| Balanced | 50 / 50 | -29 % | 100 % | 43,6 % | 37 % | 370 $ |
| Growth | 30 / 70 | -40 % | 100 % | 58,5 % | 34 % | 398 $ |

→ Toutes les stratégies passent sur 10 ans ; plus de risque = plus de
chances de garder la valeur réelle du don, mais de plus fortes baisses
en cours de route.

**Liquidité, client Balanced, après un krach**

| Versement | 20 % de PE : bourses manquées (argent bloqué) | 40 % de PE |
|---|---|---|
| 6 % | 0 % | 9,4 % |
| 7 % | 1,7 % | 28,1 % |

---

## 12. Fichiers

```
app.py                     webapp Streamlit (à lancer depuis la racine)
requirements.txt           dépendances
.env / .env.example        clés d'API (le vrai .env n'est pas versionné)
pytest.ini                 configuration des tests
scholarfund/               le moteur
  finance.py               allocation, private equity, taxe d'accise, poches,
                           simulations, tests, recommandation
  analysis.py              analyse complète pour un scénario
  ethics.py                filtre éthique
  llm_explainer.py         explication par Azure OpenAI et contrôle des chiffres
  config.py                lecture des clés d'API depuis .env
  check_connections.py     vérification des connexions
  sources/                 market_data.py (Yahoo Finance), fred_data.py,
                           finnhub_data.py, wikirate_data.py
webapp/                    model.py (adaptateur webapp ↔ moteur),
                           llm.py (chat de l'analyste IA)
tests/                     tests automatiques hors ligne
docs/                      ce document, scripts de présentation et de démo
templates/                 exemples du template Azure OpenAI (main.py,
                           embeddings.py, README d'origine)
reports/                   explications générées par le LLM
.cache/                    résultats du filtre éthique du jour
```

---

## 13. Limites et prochaines étapes

**Limites connues**

- Le passé ne prédit pas l'avenir ; 19 ans d'historique ne contiennent
  pas toutes les crises possibles.
- Sur l'horizon par défaut de 10 ans, les tests de financement passent
  presque toujours à 4 % de versement : ils ne départagent plus les
  stratégies. La préservation de la valeur réelle, seulement affichée,
  devient l'indicateur utile.
- Le private equity a un rendement fixe supposé de 9 % : il paraît plus
  sûr et plus rentable qu'il ne l'est. C'est pourquoi un fonds à 40 % de
  PE garde mieux sa valeur réelle dans le modèle, alors qu'il est moins
  liquide.
- La taxe d'accise ne porte que sur les plus-values réalisées (pas sur
  les dividendes et intérêts).
- Le filtre éthique n'examine qu'une petite partie de chaque fonds.

**Prochaines étapes**

1. Valider les seuils avec l'équipe : horizon de 10 ans, 90 % de
   réussite, ampleur des chocs. Le test du krach (-40 % sur les actions
   dès le premier mois, 90 % de réussite exigés) est ce qui rend le
   modèle prudent : il favorise toujours les stratégies avec peu
   d'actions.
2. Ajouter un critère de préservation du capital réel (corrigé de
   l'inflation).
3. Relire des explications pour d'autres profils et politiques.
4. Vérifier les faits Harvard affichés (`HARVARD` dans `webapp/model.py`).
5. Utiliser éventuellement Finnhub (actualités) dans l'explication.

---

> **Avertissement** — Prototype éducatif uniquement. Les données
> historiques et les scénarios de stress ne garantissent pas les résultats
> futurs. Ce document ne remplace ni une revue complète du code ni un
> conseil financier professionnel.
