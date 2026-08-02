# Mimari Diyagramlar — C4 Model

SeekBind'in mimarisi tek bir dev diyagramda değil, [C4 model](https://c4model.com)'e
göre 4 ayrı zoom seviyesinde belgeleniyor — her dosya farklı bir soruya
cevap veriyor, birbirinin yerini tutmuyor. Sırayla okunması öneriliyor
(her seviye bir öncekinin üzerine yakınlaşıyor):

| Seviye | Dosya | Hangi soruya cevap verir | Kimin için |
|---|---|---|---|
| 1 — Context | [1-context.md](1-context.md) | SeekBind bir bütün olarak kimlerle/nelerle konuşuyor? | Herkes — teknik olmayanlar dahil |
| 2 — Container | [2-container.md](2-container.md) | SeekBind'in içinde hangi büyük parçalar var, aralarındaki ilişki ne? | Projeye yeni katılan biri |
| 3 — Component | [3-component.md](3-component.md) | Backend API container'ının içi nasıl bölünmüş? | Backend koduna dokunacak biri |
| 4 — Code | [4-code-request-lifecycle.md](4-code-request-lifecycle.md), [4-code-provider-fallback-cache.md](4-code-provider-fallback-cache.md) | Belirli bir akış (örn. `/recommend` isteği) TAM OLARAK, adım adım nasıl işliyor? | O akışı debug edecek/değiştirecek biri |

**Neden ayrı dosyalar:** Tek bir diyagramda hem "sistem ne yapıyor"
sorusunu hem de "bir isteğin 6 dallanma noktasıyla birlikte tam akışı"
sorusunu cevaplamaya çalışmak, ikisini de kötü cevaplıyor — Context/
Container seviyesindeki biri sequence diyagramının detayında kayboluyor,
Code seviyesini arayan biri de context olmadan neye baktığını
anlamıyor. Her dosya tek bir zoom seviyesinde kalıyor.

`docs/database_schema.md` (ER diyagramı) bu şemanın biraz dışında kalan
ama benzer mantıkla ayrı tutulan bir başka referans — veri modeline
odaklanıyor, davranışa değil.
