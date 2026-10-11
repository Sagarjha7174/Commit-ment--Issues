Yes. We can build Green Home Score for tenants, homeowners, landlords, and housing societies, with climate, location, building structure, legal restrictions, finances, and future life changes all influencing the recommendations.

The important design choice is that these shouldn't be disconnected features. They should feed into one decision engine.

## The expanded product

[Mid adult man checking and paying bills using his smart phone at home](https://images.openai.com/static-rsc-4/n8ek4U1kRRijzNOzcICq2s1zazc75BrGdiw1IGsr-CqJDhtSRCj7tMr_HYC5OvtRtLszMDBkS3rq8HzBSAlK8UTvE3F3ZA7RCFqF19vfXlaaHtxEOTKcH8rkOjdeCOexf915QQZsFf_986E1sB9goiGAGvRW-lTfMwtwBJD8U9ck0B3h0TsJ53EVOlOD7-pt?purpose=inline)

1\. User & occupancy profile

Tenant or owner, renting or selling, expected stay, future occupants, household size, temporary vacancy, and likely changes in usage.

[一戶建以及區分公寓大樓的差異｜台灣三井不動產 投資顧問部](https://images.openai.com/static-rsc-4/jnFWvSs9XEV4qw0xOGCP5K7qJLihtDXWJMKtFW2enSN0cpJZlR__Ug9gl_n938t82sIbPbdCjfrQD-tZ2QEMNl0u6QPwk1SKsa-nEpba7riVH5DYZBsZoYMwN0nOTWBrWpzBukg4jCqCYLoIh2im5XjF2UK42o3y1MXQsyptGP0?purpose=inline)

2\. Building intelligence

Apartment floor, top-floor or corner exposure, standalone or duplex house, housing society, shared walls, roof access, insulation, orientation, and existing systems.

[World Environment Day 2025: Bengaluru RWAs lead the way with rainwater harvesting, solar power, and eco-friendly cutlery | Real Estate News](https://images.openai.com/static-rsc-4/4RQUAr5jEh4hO1jnpSZDIbsfTBhezpoUTyXo0i1pemQizOA-pQD_s0hty0mHM2k0VvS4m3NOFRsv3R37T6f516OgC1ncgzCLmnpkBhliuAExbE0RUEyvSRsBghg0txXzlq6dvfc_EoVrocxwhKEYnqctbnH4aYSK6OgyP0yAlas?purpose=inline)

3\. Location & climate intelligence

Local weather, heating or cooling demand, humidity, flood and heat risks, solar potential, electricity tariffs, energy sources, incentives, and local installation costs.

[Woman remodeling her house and talking to the contractor](https://images.openai.com/static-rsc-4/YsYODenzEcYW3Dkiy_I5iYcmi-EKbGKlix5wTrKabM98DkUKHaWCfeNm0HSsT6bhufjX7cbrR8F4Sn6IqXOW8chPexpDgRN2zmEYAqO-Cpo8VgSlKBux0wV1yGW8I9WUHnuBp23uok9M081eBJ1OCOrp_3_9gRL6Jt9oX8Iz0XZiEsnuElaMfJ6fKJYnNfwI?purpose=inline)

4\. Legal & technical feasibility

Landlord consent, housing-society approval, roof and facade rights, electrical capacity, planning restrictions, grid connections, and installation requirements. Unknown permissions must remain unverified, not be treated as approved.

[A serious Asian woman checking her electric bills and planning her household expenses.](https://images.openai.com/static-rsc-4/9p4kZJjwnxJFNQ59-8c0r3pD-iF_sunE_08anaLVoyIURqhjLFE5hW5wjSLOKt9bnDsnHNkzSJjn_k0wtise16BxwoS32P6qODno1KPg9e8YPM0qgpYt5_aV-PtC6FF8rCk_umBkq8YLKwZbZJ1WM8lH5p07CtfSZfsB6eHJDudX18kxb3GP7-eKxuc2kmT7?purpose=inline)

5\. Personal financial resilience

Upfront budget, affordable monthly spending, financial buffer, expected stay, willingness to take financial risks, and access to verified grants or subsidies. Employment stability can be represented through optional user-provided scenarios rather than inferred from personal data.

[Refurbishment vs. Retrofit: A Homeowner’s Guide to Sustainable Renovation — MW Architects](https://images.openai.com/static-rsc-4/ry_F5FNq_AeRqspzdhevwHbLbr1_ha7lfYbSFgj3GZPUijiCUjuB8Qg2vZl5-CaDDh8bluAxU91bMM3T0Z6kTKV0EeN_UHTooZPlWKQJ27JqNdiBC_nvDRK9_lvMCpM7ovXosBAV2qSG3srf87H44raf3IpZacZ05OIxzGZOYm0?purpose=inline)

6\. Lifecycle & uncertainty engine

Appliance upgrades, changing occupants, new tenants, relocation, vacancy, changing energy prices, and other plausible disruptions. Compare how retrofit recommendations perform under different futures.

## How they work together

Suppose a tenant lives on the top floor of an apartment in a hot, humid city, expects to move in two years, has a limited budget, and cannot modify the building exterior without permission.

The system shouldn't recommend rooftop solar or expensive permanent insulation just because those measures look good in isolation. It should first check feasibility, then prioritise appropriate low-cost or reversible improvements, estimate their benefits, and account for the short occupancy period.

A homeowner in a standalone house in the same city might receive a very different recommendation.

Same climate. Different building. Different rights. Different finances. Different answer.

## One crucial distinction

The product should maintain three separate kinds of constraints:

- Hard constraints: legal restrictions, physical impossibility, safety requirements.
- User constraints: budget, time horizon, ownership status, and personal preferences.
- Optimisation objectives: energy savings, carbon reduction, comfort, affordability, and long-term value.

Hard constraints determine what is possible. User constraints determine what is practical. Optimisation determines which feasible option is preferable.

We should also keep the tenant's interests, landlord's interests, and building-wide benefits distinct, since the person paying for an improvement may not be the person receiving its savings.

This is a coherent product direction. The next question is how broad we want the first version to be: a system that recommends improvements for one property and one decision-maker, or a system that models the entire property lifecycle across changing occupants and circumstances. The second is substantially more ambitious, so the distinction matters before we commit to a design.