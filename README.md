# Progetto di Tesi – Frammentazione e traduzione delle interrogazioni SQL

Questa cartella contiene il codice e gli script utilizzati per la parte pratica della tesi.  
Lo scopo principale è **simulare l’esecuzione di query su un database frammentato**, analizzando la traduzione delle interrogazioni e i relativi piani di esecuzione.

---

## Struttura della cartella

- **/output**  
  Dataset di partenza (estratti da *Synthea*) utilizzati per popolare il database.

- **/sql**  
  Script SQL per la creazione delle tabelle, inserimento dei dati e definizione dei frammenti.

- **Notebook Python** con esperimenti interattivi e test sulle query.  
  La traduzione delle interrogazioni è stata divisa in tre casi principali, ognuno gestito in un notebook dedicato:
  - **Query1**: interrogazioni del tipo `SELECT x FROM y WHERE c`  
  - **Query2**: interrogazioni con clausola `GROUP BY`  
  - **Query3**: interrogazioni con clausola `GROUP BY` e condizione in `HAVING`  

---

## Tecnologie
- **PostgreSQL** per la gestione del database  
- **Python 3.13** con librerie standard  
- **PyCharm** come ambiente di sviluppo  

---

## Note
- I frammenti sono gestiti tramite viste e script SQL dedicati  
- Alcune funzioni Python stampano il piano di esecuzione per verificarne la correttezza  
- I dati di partenza provengono da **Synthea**, un generatore open source di dati sanitari sintetici:  
  - Sito ufficiale: [https://synthea.mitre.org/](https://synthea.mitre.org/)  
  - Repository GitHub: [https://github.com/synthetichealth/synthea](https://github.com/synthetichealth/synthea)

---

## Cose ancora da implementare
- [ ] Aggiungere più dati al database 
- [ ] Valutare l’inclusione (o esclusione) dei casi con esecuzione *parallel* (per ora implementato sono in 'Query1')
- [ ] Costruire un set di query più ampio per testare le varie tipologie di interrogazioni  
- [ ] Creare un’interfaccia minimale per lanciare query e visualizzare i risultati  
