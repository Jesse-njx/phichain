# Geometric center, accepted contact region and fingers

The source-derived world contact point in our timelines is the note’s geometric center when it reaches its line. It is useful for explaining presentation, but is not a complete hitbox model. A distinct center does not prove an independent required finger.

In the primary open-source [Phira judgment implementation](https://github.com/TeamFlos/phira/blob/ac4795fff2efd4cb2c7ef212bbbf74bdb4c42ae3/prpr/src/judge.rs#L523), touches are transformed into every line’s local coordinates. The [sustain check](https://github.com/TeamFlos/phira/blob/ac4795fff2efd4cb2c7ef212bbbf74bdb4c42ae3/prpr/src/judge.rs#L709) tests lateral local-x proximity and may reuse any touch for each hold; it does not impose a local-y distance condition. Fresh taps select an eligible attack separately. This source describes Phira, not the closed official Phigros implementation; no exact official hitbox/tolerance equivalence is asserted.

The resulting **inference** is that perpendicular judgment strips can intersect at a shared sustained-contact position even when rendered centers differ. Der Schneid IN at70.000s supplies a concrete source example. Four active source holds lie on lines1,2,3,0. Their current geometric centers are(0,-.3),(.4,.083333),(-.4,.083333),(0,-.3), respectively, in the centered1350×900 canvas. Main horizontal lines0/1 require the central lateral coordinate; side vertical lines2/3 share the corresponding horizontal strip at y=.083333. Under the referenced simulator rule, the point(0,.083333) is a candidate shared held contact. A separate fresh tap at x=-.277778 can therefore have an independent second touch. This is a mathematical eligibility hypothesis, not an official playtest or a comfortable hand solution.

![Source center versus simulator strip hypothesis](judgment-center-vs-strip.png)

The four raw holds are62.702703→70.270270,64.864865→70.270270,67.027027→70.270270 and69.189189→70.270270s. Carrier motion through the full durations, hold initialization, release windows, fresh-attack consumption, flick gesture detection and actual runtime rules still matter. Head coordinates alone are especially misleading because these carriers move after initialization. Native conversion currently refuses exact beat precision, so this passage has no purported faithful native gameplay preview.

For normal authoring with one main playing line, distinct lateral targets and explicit finger labels provide a conservative reservation model. Existing MCP contact guards and the original chart QA use that declared compositional model, not a proof of minimum fingers for arbitrary official gimmicks. Finger demand, a rendered point, a source note count and accepted touch region must remain separate concepts.

Pinned source commit `ac4795fff2efd4cb2c7ef212bbbf74bdb4c42ae3`; [provenance](judgment-source-provenance.json).
