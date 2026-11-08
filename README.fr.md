# guarded-agent-kit (résumé en français)

Kit de départ pour faire tourner un agent Claude Code sans surveillance, en tâche planifiée, avec des limites strictes : argent, comptes, exactitude des faits, dépense quotidienne.

Il vient d'un agent qui tourne chaque jour depuis le 30/10/2026, plusieurs séances par jour. Gain à ce jour (08/11/2026) : **0 €**. Ce qui se réutilise, ce sont les garde-fous.

Deux niveaux : le code impose STOP (sans contournement), une séance à la fois, le plafond de dépense du jour, la liste d'outils permis et le remplissage de la charte ; la charte, elle, n'est que du texte que le modèle lit à chaque séance.

- `template/CLAUDE.md` : la charte (en anglais) : limites absolues, règle de vérité (VÉRIFIÉ / NON VÉRIFIÉ, avec source et date), règles de commerçant, méthode d'expérience, paliers d'argent accordés par le propriétaire seul, rapport quotidien.
- `runner/run_agent.py` : une séance. Refus de démarrer si un fichier `STOP` existe, si une autre séance tient le verrou, ou si la dépense du jour a atteint la limite. Priorité basse, attente pendant un jeu ou un rendu. Coût consigné dans `COSTS.jsonl`. 17 tests sans réseau.
- `tools/new_agent.py` crée un dossier d'agent ; `tools/scan_private.py` cherche les données privées avant publication (e-mails, chemins d'utilisateur, clés, IBAN, téléphones, vos propres termes).

Démarrage : `uv run python tools/new_agent.py C:/agents/mon-agent`, puis voir le README anglais. Licence MIT, sans garantie : vous répondez de ce que votre agent fait en votre nom.
