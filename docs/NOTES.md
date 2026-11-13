# Öğrenme Notları

## Faz 0: Keşif
- MaleCNS hem beyni hem VNC'yi (ventral sinir kordonu) içerdiği için LC4/LPLC2 → Giant Fiber (DNp01) → TTMn yolunun tamamı tek veri setinde var; FlyWire (yalnız beyin) ile bu mümkün değildi.
- Hücre tipi adlarını sorguyla doğruladık: GF = `DNp01`; LC6'nın GF'ye doğrudan sinapsı yok, bu yüzden giriş olarak LC4 ve LPLC2 seçildi.
- "Her tohumun 2 komşuluğu" yaklaşımı 30–87 bin nörona patladı. Bunun yerine "yol üzerindeki" (on-path) nöronları aldık: girişlerden ≤2 adım aşağıda VE çıkışlara ≤2 adım yukarıda olanlar. Bu, devrenin işlevine katkı verebilecek nöronları seçmenin grafik-kuramsal bir yolu.
- Eşik (min sinaps sayısı) bir gürültü filtresi gibi çalışıyor: 10'da 3.813 nöron kaldı; 20'de GFC ara nöronlarının yarısı kaybolup GF → GFC2 → TTMn yolu kırıldı.
- Önemli bilimsel uyarı: GF'nin TTMn ve PSI'ya giden asıl bağlantısı elektriksel sinaps (gap junction, shakB). EM konnektomu yalnız kimyasal sinapsları görür; bu yüzden model GF'nin gücünü olduğundan düşük gösterebilir.

## Faz 1: Veri katmanı
- `fetch_circuit.py` neuPrint'e konuşan tek dosya; sonucu parquet olarak önbelleğe alıyor. Uygulama çevrimdışı çalışıyor ve aynı veriyle tekrar üretilebilir (manifest.json neyin, ne zaman, hangi eşikle çekildiğini kaydediyor).
- Bağlantıları seyrek bir matris W (post × pre) olarak tutuyoruz: 3.813² ≈ 14,5 milyon hücreden yalnızca 88 bini dolu (%0,6). Seyrek format hem bellek hem hız için şart.
- CSR satır dilimlemede, CSC sütun dilimlemede hızlıdır. Simülasyonda "spike atan presinaptik nöronların sütunlarını" alacağımız için ikisini de tutuyoruz.
- Dale ilkesi: bir nöron tüm çıkışlarında aynı nörotransmitteri salar; bu yüzden işaret (+1/−1/0) nöron başına, yani W'nin sütunlarına uygulanıyor. İşaret sırası: tip istisnası → consensusNt → hücre tipi tahmini → varsayılan.
- Glutamat sinek merkezi sinir sisteminde GluClα kanalı üzerinden çoğunlukla inhibitör; dopamin/oktopamin/serotonin hızlı işaret taşımadığı için 0 alındı. Hepsi config'den değiştirilebilir.
- Gap junction'lar konnektom verisinden ayrı bir tabloda tutuluyor (`extra_edges`), böylece "veri" ile "literatüre dayalı varsayım" asla karışmıyor.
