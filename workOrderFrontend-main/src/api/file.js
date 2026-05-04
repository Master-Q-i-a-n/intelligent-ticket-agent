import request from './http'

export function uploadFile(data, kind) {
  const formData = new FormData()
  formData.append('file', data)
  if (kind) {
    formData.append('kind', kind)
  }

  return request({
    url: '/files/upload',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}
