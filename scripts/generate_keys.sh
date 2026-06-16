#!/usr/bin/env bash
# Generates RS256 key pair for JWT signing.
# Output: private_key.pem and public_key.pem in current directory.
set -euo pipefail

openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem

echo "Keys generated:"
echo "  private_key.pem → JWT_PRIVATE_KEY"
echo "  public_key.pem  → JWT_PUBLIC_KEY"
echo ""
echo "Copy PEM contents (including headers) into .env"
echo "IMPORTANT: Never commit private_key.pem"

JWT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA2vGXDWmJlN+miO4fyK/KNsEKcWInVdD9Y/SIP/At+EA3zAzP
yJ7aroBLSJVDUVhlFdtUA7UqKdJQj4PKm8UI+wVLDvdt9MHnxbECufTIL4vGeq41
mBjvTF8I2Ygb5Oe5ewTFfeg6IQREbds7/5WXMdZQQUsc2RGDTy2UVicAkMA+lqVs
8fQBVlRw1tAso3F5IAcXnxAd1ZTcUrFpf4E645gn+tm/zaIl5XcU9k9+7oPdCPIe
pE4crZVOYzldOXsBn/EoHZTAxtQ4B5E5yBkp6f5APhEIwI5mCK0x451vcZKCqRYj
cQECNHoaXMlq5Y9NcvOleqsT+2LT/li6N7QoGwIDAQABAoIBABaggyDiuFJHbtmV
6nj+GeLgvmiLYU9QIu/SlMYu10FhuaJ/7HVqXWVNYvpkWqmsff3tRdiAP5RE5Qh/
8U955Hy0xlYMojN6Wq6mpYZ8Urf/NQr2uBk48notFCgPFfrpK9UX4CUr+93vp/bG
goPefNqssGyfC6MvWSe0qTDiJP/QfWQ4L6zaQ59J0Nga4Un5YaKAQnsm+Cre3CB8
gWrhmPLHCda9k+IRrnhTgN9FpBALUIdWs9adoViHcISdy99/OKNGGhBDlDfQdfEL
lXGyZnZ9GscNZGFUi8RNJFiaH46iG4gPVxinkKnqh8O/xXRaMlPkDS/kHpVpj6BS
NbTHq7ECgYEA+nlFnvQVKTzDBVA7fwyUNrRr/vUizff/Fkp+s0ArbLqRdws/d9kg
wZkr+RDYLC5qgLMU84ZRVJmqGFchXVcYkb8UnizLCP7u+/LL4mh8xNPdbDvZ24CC
XXh0tPamxz4oHaMuzsf6eFw5E45WrfECapy+J9WyWZR17mWXr0/Zc/MCgYEA38Y6
4X5YYbx1B4R5fK9x5H+3yPjK540wg9+7M3Rm27cbJ2aI1UEPo8wCy6lZab4x6DxX
li80iKXv7xmTUCeDDQUoFSIzy9YU3kmNuSThSwK3g+kcoHdigncDbyOtD1vCAI1M
Pj8rJt+nqGqbD1kt86c2eHfn4/Vz8c9DhGyCDTkCgYBEsbnsbFjZZHbAIE8Q+ywz
DKyJ0kVnY9qsDGZPVwwR1+FJWuZfQkd/kTjEKGCBTYGcJoFagL4Ri8tgvZTC+r4c
SuGmt/Y/U1vL8b0FLU761Hhn1MpdLxOR+xVXBEadYmiyKC0QPTxugiyNNn6DWhQl
lTN5zVwKwXLOnUJKrIWhDQKBgQCen23tmhocbfKnOYjEkbkyODaXB4UNTlAtqtKQ
Ttr6tHlTHKOyR0RG3767j3gKNQA7l0qe8ydSFg5WdtKt5tRGznjzQiNlQoPYbls/
+pyZB3v+zae1N+tkf+i3R5rNYEXNDlwVY8G69J9sCuWPo6+nH8jE7Ho8ZSmjJ0C9
Bg3KQQKBgQDAZAzLyv+WgYUPuqmwT4m1ccWVzHHn9t8W5GoO622A9Xd5Qvr26el3
Wbn2P1pgsf4Qix19W9IlqLTw8+K0hmsb2tluQMCtN/hQjGNG7dE4+2oG/p380UY8
XfFU66cLfN5eVlIU8D92jsA6wsLRcbYAs3Ie5rJwYe7SjzyDvmPtVw==
-----END RSA PRIVATE KEY-----"

JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2vGXDWmJlN+miO4fyK/K
NsEKcWInVdD9Y/SIP/At+EA3zAzPyJ7aroBLSJVDUVhlFdtUA7UqKdJQj4PKm8UI
+wVLDvdt9MHnxbECufTIL4vGeq41mBjvTF8I2Ygb5Oe5ewTFfeg6IQREbds7/5WX
MdZQQUsc2RGDTy2UVicAkMA+lqVs8fQBVlRw1tAso3F5IAcXnxAd1ZTcUrFpf4E6
45gn+tm/zaIl5XcU9k9+7oPdCPIepE4crZVOYzldOXsBn/EoHZTAxtQ4B5E5yBkp
6f5APhEIwI5mCK0x451vcZKCqRYjcQECNHoaXMlq5Y9NcvOleqsT+2LT/li6N7Qo
GwIDAQAB
-----END PUBLIC KEY-----"

CREDENTIAL_ENCRYPTION_KEY=b2g20gpt5etWhePC9gcIsMXKFgdTa7ds1XB7kdshHP0=
