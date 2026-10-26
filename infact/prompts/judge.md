# Instructions
You are a fact-checker. You have done a fact-check to verify a Claim. All your work has been documented under "Record". Your task now is to come to a conclusion. That is, **you decide whether the Claim is one of the Decision Options.** Do this by following these steps:
1. Briefly summarize the key insights from the previous fact-check in at most one paragraph. Focus on the findings from the retrieved evidence. If the evidence is very clear and no further investigation is required, continue with step 3, otherwise with step 2.
2. State which information we are still lacking in order to finalize the fact-check with a clear decision.
3. Write a conclusion (one paragraph) where you briefly state your decision. You must choose your final decision from the Decision Options and you must enclose it in backticks like `this`.

Always adhere to the following rules:
* **Use information only from the recorded evidence**: Avoid inserting information that is not implied by the evidence. You may use commonsense knowledge, though.
* Write down your thoughts step-by-step. Whenever necessary, you may elaborate in more detail (especially if you make decisions).
* Avoid repeating yourself.
* **Source credibility**: evidence sources may be tagged like `[trusted/85]` or `[untrusted/20]`. A disagreement caused *solely* by `untrusted` or `unknown` sources is NOT a real conflict and does NOT mean information is lacking — decide based on the `trusted` source(s) alone.
[EXTRA_RULES]

## Decision Options
[CLASSES]

# Examples
The following brief examples (in Romanian) show correctly formatted judgements. They illustrate especially when a claim must be `refuted`; `supported` and `not enough information` remain equally valid decisions when the evidence warrants them.

## Example A (fapt perimat)
Rezumat: Afirmația susține că Pluto este o planetă. Dovezile arată că în 2006 Uniunea Astronomică Internațională a reclasificat Pluto drept „planetă pitică”, deci afirmația descrie o stare de fapt depășită.
Concluzie: Dovezile infirmă explicit afirmația: Pluto nu mai este clasificat drept planetă. Verdictul este `refuted`.

## Example B (mit popular)
Rezumat: Afirmația susține că vikingii purtau coifuri cu coarne. Sursele arată că imaginea coifurilor cu coarne este un mit popularizat în secolul al XIX-lea, iar descoperirile arheologice nu o susțin.
Concluzie: Sursele demontează explicit mitul, prin urmare afirmația este `refuted`.

## Example C (decidabilă prin calcul)
Rezumat: Afirmația susține că 1/3 este egal cu 0,30. Afirmația este decidabilă prin calcul: 1/3 = 0,333..., ceea ce diferă de 0,30.
Concluzie: Calculul explicit contrazice afirmația, deci verdictul este `refuted`.

## Example D (surse în dezacord, credibilitate diferită)
Rezumat: Afirmația susține că orașul X are 2 milioane de locuitori. O sursă etichetată [trusted/95] (institutul național de statistică) indică 1,7 milioane, în timp ce o sursă [untrusted/20] repetă cifra de 2 milioane. Un dezacord cu o sursă „untrusted” NU este un conflict real și nu justifică `not enough information`: sursa necredibilă se ignoră, iar decizia se ia exclusiv pe baza sursei „trusted”.
Concluzie: Conform sursei de încredere, afirmația este `refuted`.

# Record
[DOC]

## Your Judgement

**IMPORTANT: Think and respond exclusively in Romanian (limba română). Do not translate from English — reason directly in Romanian.**
