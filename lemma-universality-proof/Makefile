# Lemma Universality Formal Proof Makefile

# Coq configuration
COQC := coqc
COQDEP := coqdep
COQDOC := coqdoc

# Project configuration
PROJECT_NAME := LemmaUniversality
THEORIES_DIR := theories
BUILD_DIR := _build
DOC_DIR := docs

# Source files (automatically discovered)
VFILES := $(shell find $(THEORIES_DIR) -name "*.v" | sort)
VOFILES := $(VFILES:.v=.vo)
GLOBFILES := $(VFILES:.v=.glob)

# Default target
all: $(VOFILES)

# Build individual .vo files
%.vo: %.v
	@echo "Building $<..."
	$(COQC) -R $(THEORIES_DIR) $(PROJECT_NAME) $<

# Generate dependencies
.depend: $(VFILES)
	$(COQDEP) -R $(THEORIES_DIR) $(PROJECT_NAME) $(VFILES) > .depend

# Include dependencies if they exist
-include .depend

# Clean build artifacts
clean:
	find $(THEORIES_DIR) -name "*.vo" -delete
	find $(THEORIES_DIR) -name "*.vok" -delete  
	find $(THEORIES_DIR) -name "*.vos" -delete
	find $(THEORIES_DIR) -name "*.glob" -delete
	rm -f .depend

# Generate documentation
doc: $(VOFILES)
	mkdir -p $(DOC_DIR)
	$(COQDOC) -R $(THEORIES_DIR) $(PROJECT_NAME) --html -d $(DOC_DIR) $(VFILES)

# Verify all proofs
verify: $(VOFILES)
	@echo "All proofs verified successfully!"

# Quick syntax check
check:
	@for file in $(VFILES); do \
		echo "Checking syntax of $$file..."; \
		$(COQC) -R $(THEORIES_DIR) $(PROJECT_NAME) -i $$file || exit 1; \
	done

# Development helpers
.PHONY: all clean doc verify check depend

# Force rebuild of specific modules
foundations: theories/Foundations/LambdaCalculus.vo theories/Foundations/Credentials.vo theories/Foundations/Packages.vo

cryptography: theories/Cryptography/Ed25519.vo theories/Cryptography/OPRF.vo theories/Cryptography/BloomFilter.vo theories/Cryptography/ZKP.vo

performance: theories/Performance/TimingBounds.vo theories/Performance/Caching.vo theories/Performance/Throughput.vo

universality: theories/Universality/CryptoUniversality.vo theories/Universality/PerfUniversality.vo theories/Universality/FuncUniversality.vo

main: theories/Main/UniversalityTheorem.vo



