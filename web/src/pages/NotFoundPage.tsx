import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { usePageMeta } from '../components/layout/pageMeta'
import { Card, EmptyState } from '../components/ui/primitives'

export function NotFoundPage() {
  usePageMeta({ title: 'Not found' })
  return (
    <div className="page page-narrow">
      <Card>
        <EmptyState icon={<Compass />} title="This page does not exist" action={<Link to="/" className="btn btn-primary">Go home</Link>}>
          The link may be old, or the address mistyped.
        </EmptyState>
      </Card>
    </div>
  )
}
