import { Link, Route, Routes } from 'react-router'
import { QuizFlow } from './QuizFlow'
import { Button } from '@mui/material'
import { FlowLayout } from './components/FlowLayout'
import { StatusScreen } from './components/Presentation'

function App() {
  return (
    <Routes>
      <Route path="/" element={<QuizFlow />} />
      <Route
        path="*"
        element={
          <FlowLayout active={false} busy={false} step={null} onExit={() => {}}>
            <StatusScreen
              tag="ISE DAY"
              title="Página não encontrada"
              actions={
                <Button component={Link} to="/" variant="contained">
                  Voltar ao início
                </Button>
              }
            >
              Volte ao início para descobrir suas afinidades.
            </StatusScreen>
          </FlowLayout>
        }
      />
    </Routes>
  )
}

export default App
