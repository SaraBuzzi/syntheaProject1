# Progetto di Tesi – Frammentazione e traduzione delle interrogazioni SQL

Questa cartella contiene il codice e gli script utilizzati per la parte pratica della tesi.  
Lo scopo principale è **simulare l’esecuzione di query su un database frammentato**, analizzando la traduzione delle interrogazioni e i relativi piani di esecuzione.

## Struttura della cartella
- **/sql**  
  Script SQL per la creazione delle tabelle, inserimento dei dati e definizione dei frammenti.
  
- **/notebooks**  
  Notebook Python con esperimenti interattivi e test sulle query. In particolare la traduzione delle interrogazioni è stata divisa in tre casi, ognuno di essi gestito in un notebook:
  - Query1: interrogazioni del tipo 'SELECT x FROM y WHERE c'
  - Query2: interrogazioni che comprendessero la clausola GROUP BY
  - Query3: interrogazione che oltre a GROUP BY avessero anche la condizione in HAVING

- **/data**  
  Dataset di partenza (estratti da **Synthea**) utilizzati per popolare il database.

## Tecnologie
- **PostgreSQL** per la gestione del database.
- **Python 3.13** con librerie standard 
- **PyCharm** come ambiente di sviluppo.

## Note  
- I frammenti sono gestiti tramite viste e script SQL dedicati.  
- Alcune funzioni Python stampano il piano di esecuzione per verificarne la correttezza.

## Cose ancora da implementare
- [ ] Aggiungere più dati  
- [ ] Valutare l’inclusione (o esclusione) dei casi con esecuzione **parallel**.  
- [ ] Costruire un set di query di benchmark più ampio per testare le varie tipologie di interrogazioni.  
- [ ] Creare un’interfaccia minimale per lanciare query e visualizzare i risultati.  


