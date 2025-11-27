import pandas as pd

# Dosya yolları
orijinal_dosya = "Kasko2025_1.xlsx"
donusturulmus_dosya = "donusturulmus_veri.xlsx"

# Orijinal veriyi oku (header=1 ile sütun adlarını doğru al)
df1 = pd.read_excel(orijinal_dosya, header=1)
df2 = pd.read_excel(donusturulmus_dosya)

# 1. Eksik araba var mı? (Marka Kodu, Tip Kodu, Marka Adı, Tip Adı ile kontrol)
arabalar1 = df1[['Marka Kodu', 'Tip Kodu', 'Marka Adı', 'Tip Adı']].drop_duplicates()
arabalar2 = df2[['Marka Kodu', 'Tip Kodu', 'Marka Adı', 'Tip Adı']].drop_duplicates()

eksik_arabalar = pd.merge(arabalar1, arabalar2, how='left', indicator=True).query('_merge == "left_only"')
print(f"Orijinalde olup dönüştürülende olmayan araba sayısı: {len(eksik_arabalar)}")
if not eksik_arabalar.empty:
    print(eksik_arabalar)

# 2. Yıllar doğru mu aktarıldı?
yillar1 = set(df1.columns) - set(['Marka Kodu', 'Tip Kodu', 'Marka Adı', 'Tip Adı'])
yillar2 = set(df2['Yıl'].unique())
eksik_yil = yillar1 - yillar2
fazla_yil = yillar2 - yillar1
print(f"Orijinalde olup dönüştürülende olmayan yıl sayısı: {len(eksik_yil)}")
print(f"Dönüştürülende olup orijinalde olmayan yıl sayısı: {len(fazla_yil)}")
if eksik_yil:
    print(f"Eksik yıllar: {eksik_yil}")
if fazla_yil:
    print(f"Fazla yıllar: {fazla_yil}")

# 3. Her araba-yıl kombinasyonu aktarıldı mı?
comb1 = df1.melt(id_vars=['Marka Kodu', 'Tip Kodu', 'Marka Adı', 'Tip Adı'], var_name='Yıl', value_name='Fiyat')
comb1 = comb1[comb1['Fiyat'] > 0].dropna(subset=['Fiyat'])
comb2 = df2[['Marka Kodu', 'Tip Kodu', 'Marka Adı', 'Tip Adı', 'Yıl', 'Fiyat']]

eksik_kombinasyon = pd.merge(comb1, comb2, how='left', on=['Marka Kodu', 'Tip Kodu', 'Marka Adı', 'Tip Adı', 'Yıl', 'Fiyat'], indicator=True).query('_merge == "left_only"')
print(f"Orijinalde olup dönüştürülende olmayan araba-yıl-fiyat kombinasyonu: {len(eksik_kombinasyon)}")
if not eksik_kombinasyon.empty:
    print(eksik_kombinasyon.head())

print("\nTestler tamamlandı.")