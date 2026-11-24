RETURN_PERIOD = 200   # période de retour du STEC (AEP200 - moyenne)
HALF_WINDOW = 25      # demi-fenêtre de scénarios autour du 1/200 pour l'allocation d'Euler
MIN_ABS = 0.5         # |delta| sous lequel un péril est regroupé dans "Other" du waterfall

SCALE = 1e6           # les strips de py_aggregation_cat sont en unités : / 1e6 -> millions

# sorties de py_aggregation_cat lues en entrée
AGG_FILE_PREFIX = "Gross_MM_reconciliation_"  # Gross_MM_reconciliation_<entité>.xlsx
AGG_GROUP_ENTITY = "Group"                    # fichier Group (déjà en euros, sans détail par entité) : ignoré
AGG_STRIPS_SHEET = "Local_AAL_strips"         # feuille des pertes annuelles par risque
AGG_SIM_COL = "year"                          # colonne des simulations
AGG_TOTAL_COL = "Total"                       # somme des risques : contrôlée puis ignorée

LONG_COLUMNS = ["sim", "entity", "peril", "loss"]  # format long des strips

GROUP_LABEL = "Group"
PARAMETERS_SHEET = "Parameters"
OTHER_STEP = "Other"  # étape du waterfall regroupant les petits deltas
FX_STEP = "FX"        # étape du waterfall pour l'effet change

# couleurs du waterfall (hausse, baisse, totaux)
COLOR_INCREASE = "D9731A"
COLOR_DECREASE = "2F5BEA"
COLOR_TOTAL = "0B1F4D"
