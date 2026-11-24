# Catálogo del kit SVG

Generado por `python cli.py kit`. No lo edites a mano: edita `catalogo.json`.

## cerebro — Cerebro
Cerebro rosa de perfil, con circunvoluciones, cerebelo y tronco encefálico.

- Usos: cerebro, mente, decisiones, memoria, señales, dolor, pensamiento
- Partes: aura, tronco, cerebelo, cerebro
- Variables: —
- Ancho recomendado: [0.45, 0.95]  · alto/ancho: 1.0

## chispas — Chispas
Racimo de rayos amarillos brillantes.

- Usos: electricidad, dolor eléctrico, descarga, señal, energía, cosquilleo
- Partes: —
- Variables: chispa
- Ancho recomendado: [0.3, 0.95]  · alto/ancho: 1.0
- Nota: Variable chispa=#hex cambia el color. Úsala encima de otra pieza con at y anim pop+shake.

## compresion — Nervio comprimido
Un músculo presiona un nervio contra un hueso: se ven el aplastamiento, la presión y chispas de dolor.

- Usos: compresión nerviosa, nervio pinzado, presión, causa del hormigueo
- Partes: hueso, musculo, nervio, presion, chispas
- Variables: nervio
- Ancho recomendado: [0.85, 1.0]  · alto/ancho: 0.8

## corazon — Corazón
Corazón anatómico rojo con venas azules y arterias, brillante.

- Usos: corazón, latido, circulación, presión arterial, estrés, amor
- Partes: aura, vasos, corazon
- Variables: —
- Ancho recomendado: [0.35, 0.6]  · alto/ancho: 1.15
- Nota: Queda bien con anim pop+pulse.

## nervio — Nervio
Nervio vertical: cable amarillo brillante con bandas de mielina y pulso de luz.

- Usos: nervio, señal eléctrica, dolor, hormigueo, entumecimiento
- Partes: aura, cable, pulso
- Variables: nervio
- Ancho recomendado: [0.2, 0.45]  · alto/ancho: 2.5
- Nota: Es alto (2.5 veces su ancho). Variable nervio=#hex para el color (rojizo = dañado, verde = sano). Se puede repetir 2 o 3 veces.

## persona_sentada — Persona sentada
Persona de perfil sentada frente a un escritorio con laptop; cuerpo de cristal azul con los vasos y el nervio de las piernas brillando.

- Usos: sedentarismo, trabajo de oficina, estar sentado, postura, circulación en piernas
- Partes: silla, escritorio, cuerpo, vasos, nervio
- Variables: nervio
- Ancho recomendado: [0.8, 1.0]  · alto/ancho: 1.25

## pie_xray — Pie (rayos X)
Pie humano de perfil, semitransparente, con huesos, vena azul, arteria roja y nervio amarillo.

- Usos: pie, dormirse el pie, hormigueo, circulación, nervio del pie, calzado
- Partes: aura, pie, vasos, nervio
- Variables: nervio
- Ancho recomendado: [0.8, 1.0]  · alto/ancho: 1.0
- Nota: Con variable nervio=#hex cambia el color del nervio.

## pierna_xray — Pierna (rayos X)
Pierna humana de pie y de perfil, de la rodilla al pie, semitransparente, con huesos, vasos y nervio.

- Usos: pierna, rodilla, pantorrilla, circulación en piernas, nervio ciático, estar de pie
- Partes: aura, pierna, vasos, nervio
- Variables: nervio
- Ancho recomendado: [0.4, 0.55]  · alto/ancho: 2.0
- Nota: Es muy alta: su alto es el doble de su ancho. Usa w 0.5 con y 0.7 para que quepa. Variable nervio=#hex cambia el color del nervio.

## reloj — Cronómetro
Cronómetro blanco con un sector rojo que marca el tiempo.

- Usos: tiempo, minutos, duración, plazo, cuenta atrás
- Partes: —
- Variables: ang, ang_h, x, y
- Ancho recomendado: [0.3, 0.65]  · alto/ancho: 1.08
- Nota: Variables ang y ang_h son los ángulos de las agujas en grados.

## vena — Vena con glóbulos
Vaso sanguíneo horizontal ancho con glóbulos rojos dentro.

- Usos: sangre, circulación, vena, flujo sanguíneo, oxígeno
- Partes: tubo, globulos
- Variables: —
- Ancho recomendado: [1.0, 1.3]  · alto/ancho: 0.42
- Nota: Truco: dibújala dos veces, una con only=tubo (fija) y otra con only=globulos y anim slide_left para que la sangre fluya.
