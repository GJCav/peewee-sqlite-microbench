# Peewee & SQLite Performance Optimization

## Scenario

You are working on a highly parallelizable computing task, which could be distributed to several computers.  To coordinate the distribution, you choose to reserve a computer as a *coordinator*, who dispatches computing jobs to other computers, or *wokers*, saves the results and provide fast query service.

Computing is cost intensive. Once you have the result, you should keep it safe. 