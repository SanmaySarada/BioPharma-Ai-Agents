# Verify all required packages load successfully
required <- c("survival", "survminer", "tidyverse", "haven", "jsonlite", "readr", "ggplot2", "broom", "tableone", "officer", "flextable", "writexl")
for (pkg in required) {
  if (!require(pkg, character.only = TRUE, quietly = TRUE)) {
    stop(paste("Package not available:", pkg))
  }
}
cat("All packages loaded successfully\n")
