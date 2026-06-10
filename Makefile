# Loblaw Bio — immune cell population analysis
# Grader entrypoints: setup, pipeline, dashboard.

PYTHON ?= python

.PHONY: setup pipeline dashboard clean

# Install all dependencies.
setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

# Full pipeline: initialize DB + load data (Part 1), then run analyses (Parts 2-4).
pipeline:
	$(PYTHON) load_data.py
	$(PYTHON) run_pipeline.py

# Launch the interactive dashboard (local server).
dashboard:
	$(PYTHON) -m streamlit run app.py

# Remove generated artifacts.
clean:
	rm -f cell_counts.db
	rm -rf outputs __pycache__ src/__pycache__
