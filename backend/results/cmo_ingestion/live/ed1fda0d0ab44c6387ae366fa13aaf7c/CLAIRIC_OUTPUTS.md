# Clairic scalar extraction outputs

Synthetic manufacturing records, not actual Sanofi operational data. All candidates remain unverified.

## Request 1

Evidence: `13933da4773a48950e73351e`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 12 ; Acidity [pH]: 6,895
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999576807022095 | 0.002495383843779564 |
| elapsed_hours | null | 0.9875630048897338 | 0.9905774593353271 |
| elapsed_hours_text | "12" | 0.9999938011169434 | 0.0010711484355852008 |
| measurement_label | "Acidity" | 0.34135815501213074 | 0.3163979947566986 |
| measurement_value | 6.895 | 0.9871134490877419 | 0.0003636580368038267 |
| measurement_value_text | "6,895" | 0.9177901148796082 | 0.01153804361820221 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_label: uncertain presence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 2

Evidence: `e9a1eac95fa844ee87cea0e9`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 0 ; Acidity [pH]: 7,139
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999665021896362 | 0.0021323480177670717 |
| elapsed_hours | null | 0.9984952239413672 | 0.8978440165519714 |
| elapsed_hours_text | "0" | 0.9214587211608887 | 0.007567501626908779 |
| measurement_label | "Acidity [pH" | 0.4126925468444824 | 0.24959737062454224 |
| measurement_value | 7.139 | 0.996361340317662 | 0.0006084803026169538 |
| measurement_value_text | "7,139" | 0.9905917048454285 | 0.005238715093582869 |

Review: elapsed_hours: missing (null); elapsed_hours_text: low or missing confidence; measurement_label: low or missing confidence; measurement_label: uncertain presence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 3

Evidence: `754a7ee1132cb0540594ca5e`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 12 ; Penicillin [g/L]: 1.16
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999697208404541 | 0.0017756797606125474 |
| elapsed_hours | null | 0.9901725774496553 | 0.9849191904067993 |
| elapsed_hours_text | "12" | 0.9999960660934448 | 0.0007296131225302815 |
| measurement_label | "Penicillin [g/L" | 0.6154683828353882 | 0.021163633093237877 |
| measurement_value | 1.16 | 0.9956701743827023 | 0.0008702509221620858 |
| measurement_value_text | "1.16" | 0.797336757183075 | 0.00429496681317687 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 4

Evidence: `77ec7e2d3b482d1ad1b91b37`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 0 ; Penicillin [g/L]: 2.304
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999706745147705 | 0.0014626418706029654 |
| elapsed_hours | null | 0.9982753983949726 | 0.8502355813980103 |
| elapsed_hours_text | "0" | 0.940601646900177 | 0.006042176391929388 |
| measurement_label | "Penicillin [g/L" | 0.7129400372505188 | 0.01752587966620922 |
| measurement_value | 2.304 | 0.9988532536810698 | 3.865841426886618e-05 |
| measurement_value_text | "2.304" | 0.9054515361785889 | 0.005200847052037716 |

Review: elapsed_hours: missing (null); elapsed_hours_text: low or missing confidence; measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 5

Evidence: `12edb4b590ba5abdcb850697`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 12 ; pressure [bar]: 1.721
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999741315841675 | 0.0039719776250422 |
| elapsed_hours | null | 0.9924158546105165 | 0.9560376405715942 |
| elapsed_hours_text | "12" | 0.9999959468841553 | 0.0009232532465830445 |
| measurement_label | "pressure" | 0.5182747840881348 | 0.01362259779125452 |
| measurement_value | 1.721 | 0.9952860623127737 | 0.00021025443857070059 |
| measurement_value_text | "1.721" | 0.9547158479690552 | 0.0022196220234036446 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 6

Evidence: `88e6c631d71a4dd7d42e4e25`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 0 ; pressure [bar]: 1.697
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999748468399048 | 0.0026229347568005323 |
| elapsed_hours | null | 0.9991155348070632 | 0.5691439509391785 |
| elapsed_hours_text | "0" | 0.9772390127182007 | 0.007412491366267204 |
| measurement_label | "pressure" | 0.5873475074768066 | 0.01258794218301773 |
| measurement_value | 1.697 | 0.9869711547237165 | 0.0004490752471610904 |
| measurement_value_text | "1.697" | 0.8628759980201721 | 0.0021084563340991735 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 7

Evidence: `8b4aa6c5e070d2317be44d62`; original-element offset: 223

Source context:

```text
Batch: SYN-301 ; Hour: 0 ; environment cfu [CFU/m3]: 7.0
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999650716781616 | 0.002632423769682646 |
| elapsed_hours | 0 | 0.9997363785557283 | 0.04007625952363014 |
| elapsed_hours_text | "0" | 0.9872075915336609 | 0.0063989474438130856 |
| measurement_label | "environment cfu [CFU/m3" | 0.46937593817710876 | 0.008474229834973812 |
| measurement_value | 7 | 0.9981738036936689 | 0.0007168585434556007 |
| measurement_value_text | "7.0" | 0.9570496082305908 | 0.006505314260721207 |

Review: measurement_label: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit

## Request 8

Evidence: `b73aec9e7c36cb595964b828`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 12 ; environment cfu [CFU/m3]: 6.0
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999638795852661 | 0.003157097613438964 |
| elapsed_hours | 12 | 0.9987238289263364 | 0.34074124693870544 |
| elapsed_hours_text | "12" | 0.9999948740005493 | 0.0008951097843237221 |
| measurement_label | "environment cfu [CFU/m3" | 0.46026962995529175 | 0.008522650226950645 |
| measurement_value | 6 | 0.997974547635944 | 0.0008502087439410388 |
| measurement_value_text | "6.0" | 0.8960219025611877 | 0.00409423653036356 |

Review: elapsed_hours: uncertain presence; measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit

## Request 9

Evidence: `20e912fa897f2a398c2b3c6c`; original-element offset: 219

Source context:

```text
Batch: SYN-301 ; Hour: 0 ; bioburden [CFU/mL]: 20.0 
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999583959579468 | 0.0018136814469471574 |
| elapsed_hours | 0 | 0.9997114775881778 | 0.11692403256893158 |
| elapsed_hours_text | "0" | 0.9433863162994385 | 0.004366219509392977 |
| measurement_label | "bioburden [CFU/mL" | 0.635020911693573 | 0.0019486191449686885 |
| measurement_value | 20 | 0.9982001413271426 | 0.0003843652084469795 |
| measurement_value_text | "20.0" | 0.9244239330291748 | 0.001657526008784771 |

Review: elapsed_hours: uncertain presence; elapsed_hours_text: low or missing confidence; measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit

## Request 10

Evidence: `20e912fa897f2a398c2b3c6c`; original-element offset: 271

Source context:

```text
Batch: SYN-301 ; Hour: 12 ; bioburden [CFU/mL]: 9.0
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.999966025352478 | 0.0015377633972093463 |
| elapsed_hours | null | 0.9981813406248546 | 0.8221403360366821 |
| elapsed_hours_text | "12" | 0.9999951124191284 | 0.001159305335022509 |
| measurement_label | "bioburden [CFU/mL" | 0.6069726943969727 | 0.002156986854970455 |
| measurement_value | 9 | 0.9991836469693074 | 0.0003842435253318399 |
| measurement_value_text | "9.0" | 0.9045470952987671 | 0.003812905168160796 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 11

Evidence: `7fc61eca2c7154d0e7e91b12`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 0 ; pressure [bar]: 1.697
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999748468399048 | 0.0026229347568005323 |
| elapsed_hours | null | 0.9991155348070632 | 0.5691439509391785 |
| elapsed_hours_text | "0" | 0.9772390127182007 | 0.007412491366267204 |
| measurement_label | "pressure" | 0.5873475074768066 | 0.01258794218301773 |
| measurement_value | 1.697 | 0.9869711547237165 | 0.0004490752471610904 |
| measurement_value_text | "1.697" | 0.8628759980201721 | 0.0021084563340991735 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 12

Evidence: `b5869867e21e4f3bb8e8a22a`; original-element offset: 0

Source context:

```text
Batch: SYN-301 ; Hour: 12 ; pressure [bar]: 1.721
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-301" | 0.9999741315841675 | 0.0039719776250422 |
| elapsed_hours | null | 0.9924158546105165 | 0.9560376405715942 |
| elapsed_hours_text | "12" | 0.9999959468841553 | 0.0009232532465830445 |
| measurement_label | "pressure" | 0.5182747840881348 | 0.01362259779125452 |
| measurement_value | 1.721 | 0.9952860623127737 | 0.00021025443857070059 |
| measurement_value_text | "1.721" | 0.9547158479690552 | 0.0022196220234036446 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value

## Request 13

Evidence: `c59e48edc9e1d2ae6fe79ab7`; original-element offset: 211

Source context:

```text
Batch: SYN-3@1 ; Hour: @ ; bioburden [CFU/mL]: 20.0 
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-3@1" | 0.9999079704284668 | 0.0019153057364746928 |
| elapsed_hours | null | 0.8313321750605159 | 0.9999027252197266 |
| elapsed_hours_text | null | 0.9930904507637024 | 0.9668245911598206 |
| measurement_label | "bioburden [CFU/mL" | 0.5528188347816467 | 0.004774333909153938 |
| measurement_value | 20 | 0.9915595014314906 | 0.003227760549634695 |
| measurement_value_text | "20.0" | 0.5130361914634705 | 0.056008391082286835 |

Review: elapsed_hours: missing (null); elapsed_hours_text: missing (null); measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_value_text: uncertain presence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours_text: missing or invalid source number

## Request 14

Evidence: `c59e48edc9e1d2ae6fe79ab7`; original-element offset: 263

Source context:

```text
Batch: SYN-3@1 ; Hour: 12 ; bioburden [CFU/mL]: 9.0
```

| Field | Value | Confidence | Probability missing |
|---|---|---|---|
| batch_id | "SYN-3@1" | 0.9999586343765259 | 0.0014727083034813404 |
| elapsed_hours | null | 0.9973151597218097 | 0.8537003397941589 |
| elapsed_hours_text | "12" | 0.9999834299087524 | 0.001553522190079093 |
| measurement_label | "bioburden [CFU/mL" | 0.6308972835540771 | 0.0037122333887964487 |
| measurement_value | 9 | 0.9967674609491747 | 0.0009612147696316242 |
| measurement_value_text | "1" | 0.36856821179389954 | 0.029293574392795563 |

Review: elapsed_hours: missing (null); measurement_label: low or missing confidence; measurement_value_text: low or missing confidence; measurement_label: clipped boundary expanded using adjacent printed unit; elapsed_hours: numeric answer does not equal printed source value; measurement_value: numeric answer does not equal printed source value

