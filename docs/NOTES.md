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

## Faz 2: LIF motoru
- LIF (sızdıran entegre-et-ateşle) nöronu bir RC devresi gibidir: girdi yoksa voltaj dinlenme değerine sızar (τ_m), girdi eşiği aşarsa spike atar ve sıfırlanır. Aksiyon potansiyelinin şeklini değil, yalnızca zamanını modelliyoruz.
- Sinaptik girdi g ayrı bir değişken: her presinaptik spike g'ye (w_syn × sinaps sayısı × işaret) ekler ve g τ_syn ile söner. Böylece bir spike'ın etkisi anlık değil, birkaç milisaniyeye yayılır.
- Analitik test: sabit girdi I ile eşiğe varış süresi t = τ·ln(I/(I−Δθ)), frekans = 1/(t_ref + t). Sayısal sonucumuz bu formülle %2 içinde tutuyor; bu, Euler entegrasyonunun doğru kurulduğunu kanıtlıyor.
- Vektörleştirme: tüm denemeler (trial) ve lezyon koşulları N×B matrisinde aynı döngüde ilerliyor. Her adımda yalnızca spike atan nöronların W sütunları (CSC) alınıp küçük bir matrisle çarpılıyor: maliyet sinaps sayısıyla değil, o anki spike sayısıyla orantılı.
- Gecikme için "spike halka tamponu" kullanıyoruz: t anındaki spike'lar saklanıyor ve t+2 ms'de teslim ediliyor. Akım yerine spike sakladığımız için bellek küçük kalıyor.
- Tekrarlanabilirlik: her deneme kendi tohumuna (seed) sahip; aynı tohum, aynı Poisson girdisi demek. Lezyon karşılaştırmasında taban ve lezyon aynı girdiyi görüyor, yani fark yalnızca lezyondan geliyor (eşleştirilmiş deney tasarımı).
- İlk gözlem: girdi yoksa ağ tamamen sessiz; güçlü "looming" rampasında GF ve TTMn ateşleniyor. Ama GF ~260 Hz'e doyuyor (gerçekte bir looming'e bir-iki spike). Bu bir model uyarısı; Faz 5'te incelenecek.

## Faz 3: Yol bulucu, lezyonlar, API
- Kenar maliyeti −log(pay): pay = sinaps sayısı / hedef nöronun tüm veri setindeki toplam girdisi. Logaritma, çarpımı toplama çevirir. Böylece "en kısa yol" = "her adımda hedefin girdisinden en büyük payı taşıyan zincir" olur ve Dijkstra/A* kullanılabilir.
- Paydanın tüm konnektomdan gelmesi önemli: yalnız alt devredeki girdiye bölseydik, alt devre sınırında kalan nöronların payı yapay olarak şişerdi.
- A* araması: her düğümden hedefe kalan en düşük maliyeti (ters Dijkstra) sezgisel olarak kullanıyoruz. Bu tahmin hiçbir zaman fazla olmadığı için yollar maliyet sırasıyla çıkıyor; testte kaba kuvvetle tüm yolları sayıp birebir doğruladık.
- Sanal lezyon: nöronu "hiç spike atmaz" yapmak, W'de sütununu sıfırlamakla aynı şey. Taban ve lezyon aynı tohumlarla koşuyor (eşleştirilmiş tasarım); tabanı bir kez hesaplayıp önbelleğe alıyoruz.
- İstatistik: asıl sonuç etki büyüklüğü (Cohen's d) ve bootstrap güven aralığı. Simülasyonda deneme sayısını artırarak p-değerini istediğimiz kadar küçültebiliriz; bu yüzden p-değeri yalnızca ikincil bilgi.
- İlk bilimsel bulgu: GF lezyonu TTMn spike'larını %45 azaltıyor ama sıfırlamıyor; DNp02, DNp11 gibi paralel inen nöron yolları da TTMn'ye ulaşıyor. Tarama ise bazı glutamaterjik GF girdilerinin (ör. PVLP010) lezyonunun TTMn'yi artırdığını gösteriyor: bu "dezinhibisyon", tamamen "glutamat = inhibitör" varsayımına bağlı ve Faz 5'te test edilecek.
- FastAPI katmanı ince; tüm mantık `Service` sınıfında, bu yüzden HTTP olmadan da test edilebiliyor. Uzun süren tarama arka planda bir iş (job) olarak koşuyor ve ilerlemesi sorgulanabiliyor.

## Faz 4: Arayüz
- Grafik WebGL (sigma.js) ile çiziliyor: 3.813 düğüm ve on binlerce kenar SVG'de her karede DOM'u yeniden çizmeyi gerektirirdi; WebGL ise GPU'da tek seferde çizer.
- Yerleşim (layout) bir kez Python'da hesaplanıp önbelleğe alınıyor: kuvvet-yönelimli (bağlı nöronlar birbirini çeker, hepsi birbirini iter) ama x ekseni "sinyal akış derinliğine" çekiliyor: girişler solda, motor nöronlar sağda. Böylece animasyonda aktivitenin soldan sağa yayıldığını görebiliyoruz.
- Animasyon: simülasyon bir kez çalışıyor, sonra raster verisi zaman kaydırıcısıyla oynatılıyor. Her karede ikili arama ile son 6 ms'deki spike'lar bulunup ilgili düğümler parlatılıyor; grafik yeniden kurulmuyor, yalnızca "reducer" fonksiyonları yeniden çalışıyor.
- Raster grafiği: her satır bir nöron, her nokta bir spike. Rol ve tip sırasına göre gruplandığında popülasyon düzeyindeki dalgalar (ör. girdi rampasıyla artan aktivite) gözle görülebiliyor.
- Lezyon paneli tablo olarak d ve %95 güven aralığını öne çıkarıyor, p-değerini soluk gösteriyor: arayüz de istatistiksel yorumu yönlendiriyor.
- Küçük ama önemli bir düzeltme: bir nöronun çıkış sinapslarının işareti, hedef nöronun değil, o nöronun kendi nörotransmitterine bağlı (Dale ilkesi). GF → TTMn sinapsı uyarıcıdır, TTMn glutamaterjik olsa bile.

## Faz 5: Bilimsel sağlama
- Kalibrasyon: elektriksel sinaps gücünü literatürden sayı olarak alamadık; bunun yerine "bir GF spike'ı → tam bir TTMn spike'ı" ölçütüne göre ayarladık (300 sinaps-eşdeğeri, 2 ms gecikme). Gerçek gecikme ~0,8 ms; modelimiz 1:1 iletimi ve bu kadar kısa gecikmeyi aynı anda sağlayamıyor. Bu bir model sınırı ve açıkça yazıldı.
- Beklentinin tuttuğu kısım: girdi yoksa sessizlik; güçlü looming benzeri girdi → GF → TTMn ateşleniyor. PSI ise yalnız elektriksel sinapslarla ateşleniyor; bu, biyolojideki GF → PSI'nin elektriksel olmasıyla tutarlı.
- Tutmayan kısım: model GF seçici değil (zayıf girdide de ateşliyor) ve doyuyor (200–400 Hz). Sebep, 311 girdinin ~11 bin sinapsla tek bir nokta nörona doğrusal olarak toplanması ve tüm nöronların aynı eşiği paylaşması. Bunu sessizce parametre ayarlayarak "düzeltmedik", belgeledik.
- Duyarlılık analizi, bir sonucun hangi varsayıma ne kadar bağlı olduğunu gösterir. Burada glutamatın işareti baskın: glutamat uyarıcı sayılırsa ağın %56–80'i ateşleniyor ve GF lezyonu TTMn'yi neredeyse hiç değiştirmiyor; inhibitör sayılırsa %18–100 azaltıyor.
- Sağlam sonuç: GF, LC4/LPLC2'den TTMn'ye giden birkaç yoldan biri ve kaldırılması TTMn'yi her ayarda azaltıyor (yön sağlam). Sağlam olmayan: azalmanın büyüklüğü. Bu, GF'si susturulmuş sineklerin yine de (daha yavaş) kalkış yapabilmesiyle nitel olarak uyumlu.
- İstatistik dersi: simülasyonda denemeler arası gürültü yalnızca Poisson girdisinden geliyor, bu yüzden standart sapma çok küçük ve Cohen's d 100'ün üzerine çıkabiliyor. Bu durumda d, etkinin büyüklüğünü değil modelin sessizliğini ölçüyor; büyüklük için % değişim daha dürüst.
- Alt devre seçimi de sonucu etkiliyor: daha küçük (t=20) devrede paralel yollar azaldığı için tek bir nöronun önemi abartılıyor.

## Faz 6: Cila
- Devreden bağımsızlık testi: beslenme devresini (tat nöronları → hortum motor nöronları) yalnızca yeni bir YAML dosyasıyla ekledik; kodda tek satır değişmedi. Tip adlarını yine önce neuPrint'te sorgulayarak bulduk (ör. LB1a, claw_tpGRN, MN1–MN13).
- "Konfigürasyonla yönetilen" tasarımın faydası: devre tanımı (veri) ile algoritma (kod) ayrı. Aynı motor, aynı testler ve aynı arayüz her devrede çalışıyor.
- Tek komut (`make dev`) arka ucu ve ön ucu birlikte başlatıyor; `make test`, `make lint`, `make sanity` tekrar üretilebilirliği kolaylaştırıyor.
- Kod stili otomatik denetleniyor: ruff (Python) ve oxlint + prettier + strict TypeScript. Ruff'ın SIM kurallarını bilinçli olarak kapattık, çünkü bunlar projede kullanmadığımız ternary ifadelerini önerir.
- README, token'ın güvenli saklanmasını (yalnızca ortam değişkeni) ve verinin nasıl yeniden çekileceğini anlatıyor; sonuçların biyolojik gerçek olmadığını açıkça vurguluyor.
