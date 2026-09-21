#!/bin/bash
echo "=========================================="
echo "最終驗證檢查清單"
echo "=========================================="
echo ""

echo "1. Python 語法檢查"
python3 -m py_compile *.py && echo "   ✓ 所有 Python 檔案編譯成功" || echo "   ✗ 編譯失敗"
echo ""

echo "2. 檔案存在性檢查"
files=(
  "console_ui.py"
  "README.md"
  "CHANGELOG.md"
  "version.py"
  "prov/get_voice.txt"
  "prov/get_device_info.txt"
  "test_open_get.py"
  "demo_open_get.sh"
  "BATCH_GET_GUIDE.md"
  "IMPLEMENTATION_SUMMARY.md"
)

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    echo "   ✓ $file"
  else
    echo "   ✗ $file (缺少)"
  fi
done
echo ""

echo "3. 版本檢查"
version=$(python3 -c "from version import VERSION; print(VERSION)")
echo "   當前版本: $version"
if [ "$version" = "1.6" ]; then
  echo "   ✓ 版本正確"
else
  echo "   ✗ 版本不正確（預期 1.6）"
fi
echo ""

echo "4. 單元測試"
python3 test_open_get.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "   ✓ 所有測試通過"
else
  echo "   ✗ 測試失敗"
fi
echo ""

echo "5. 範例檔案統計"
voice_lines=$(grep -v '^#' prov/get_voice.txt | grep -v '^$' | wc -l)
device_lines=$(grep -v '^#' prov/get_device_info.txt | grep -v '^$' | wc -l)
echo "   get_voice.txt: $voice_lines 個參數"
echo "   get_device_info.txt: $device_lines 個參數"
echo ""

echo "6. 文件完整性"
docs=(
  "README.md:批次參數操作"
  "CHANGELOG.md:1.6"
  "BATCH_GET_GUIDE.md:批次 GET 參數功能指南"
)

for doc in "${docs[@]}"; do
  file="${doc%%:*}"
  keyword="${doc##*:}"
  if grep -q "$keyword" "$file"; then
    echo "   ✓ $file 包含 '$keyword'"
  else
    echo "   ✗ $file 缺少 '$keyword'"
  fi
done
echo ""

echo "=========================================="
echo "驗證完成"
echo "=========================================="
