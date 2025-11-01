After data measured by PerkinElmer is exported via TimeBase, it is formatted as time1–wavenumber–absorbance.
Simply matching it with Time2–temperature from the TG file does not allow plotting in Origin, because the temperature series is non-monotonic.
This program aligns time1 with time2, takes the nearest temperature (Temp), and when duplicate temperatures occur it offsets subsequent duplicates by +0.015 °C (the step is adjustable and represents the average temperature spacing),
thereby resolving the non-monotonicity.
<img width="1346" height="951" alt="image" src="https://github.com/user-attachments/assets/a9392e95-4669-40ee-9b38-33cb1d1a3c12" />

Additionally, the “Timebase” data-processing software is included.
