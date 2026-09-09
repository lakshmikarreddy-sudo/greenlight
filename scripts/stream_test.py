import httpx

__test__ = False


def main():
    print('Fetching samples...')
    r = httpx.get('http://127.0.0.1:8888/api/samples')
    print('status', r.status_code)
    data = r.json()
    print('samples count', len(data))
    sid = data[0]['id']
    print('Sample id', sid)
    print('Starting analysis stream...')
    with httpx.Client() as client:
        with client.stream('POST', 'http://127.0.0.1:8888/api/analyze', json={'sample_id': sid}) as s:
            for chunk in s.iter_text():
                print('CHUNK:', chunk[:200])
                if 'brief' in chunk:
                    print('Received brief chunk')
                    break
    print('Done')


if __name__ == '__main__':
    main()
