# EvalTask — Index de la documentation globale LangChain

## Description

Ce répertoire contient la documentation de référence de la plateforme EvalTask, destinée à l'apprentissage global du serveur LangChain. Ces documents sont partagés avec le serveur pour alimenter la collection ChromaDB globale (commune à tous les tenants).

## Structure

| Fichier | Contenu | Public cible |
|---|---|---|
| `01_plateforme_evaltask.md` | Présentation générale, modules, rôles, stack technique | Vue d'ensemble |
| `02_modele_donnees.md` | Schéma de données complet (62 modèles, associations, champs, enums) | Compréhension des données |
| `03_outils_assistant.md` | Catalogue des outils IA (tool calling), paramètres, retours, permissions | Orchestration LLM |
| `04_processus_metier.md` | Processus BTP : cycle projet, achats, EVM, QSSE, stock, compta, avenants | Logique métier |
| `05_guide_assistant.md` | Guide de comportement de l'assistant IA : règles, format, types de questions | Prompt système |
| `06_glossaire_btp.md` | Glossaire métier BTP : termes, acronymes, types de projets, types de contrats | Vocabulaire |
| `07_architecture_ia.md` | Architecture d'intégration Rails ↔ LangChain : JWT, RAG, sécurité, config | Technique |
| `08_connaissances_btp.md` | Connaissances sectorielles BTP : cycle de vie, acteurs, documents, réglementation, KPIs | Domaine métier |

## Utilisation

### Pour le serveur LangChain

Ces fichiers doivent être ingérés dans la collection ChromaDB globale (`evaltask_global`) via le pipeline RAG du serveur LangChain. Ils fournissent :

1. **Connaissance de la plateforme** : structure des données, outils disponibles, permissions
2. **Connaissance métier BTP** : vocabulaire, processus, indicateurs, réglementation
3. **Guide de comportement** : comment l'assistant doit répondre, quels outils appeler, quel ton adopter

### Mise à jour

Ces documents doivent être mis à jour lorsque :
- De nouveaux modèles ou champs sont ajoutés au schéma
- De nouveaux outils IA sont implémentés
- Les workflows métier évoluent (nouveaux statuts, transitions)
- La configuration de l'intégration LangChain change

### Format

- Markdown structuré avec tableaux et listes
- Pas de code exécutable (documentation pure)
- Références aux noms de modèles/champs Rails pour correspondance exacte
- Vocabulaire métier en français (langue de la plateforme)

## Métadonnées

- **Version** : 1.0 — 23 juillet 2026
- **Plateforme** : EvalTask ERP (Rails 8 + PostgreSQL)
- **Serveur IA** : LangChain EvalTask Server v2.0 (Python FastAPI)
- **Modèle LLM par défaut** : z-ai/glm-5.2 (via OpenRouter)
- **Modèle de fallback** : google/gemma-3-27b-it
