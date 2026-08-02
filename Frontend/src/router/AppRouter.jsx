import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import ProtectedRoute from './ProtectedRoute'
import LoginPage from '../pages/LoginPage'
import RegisterPage from '../pages/RegisterPage'
import ChatPage from '../pages/ChatPage'
import TaskPage from '../pages/TaskPage'
import CalendarPage from '../pages/CalendarPage'
import ReminderPage from '../pages/ReminderPage'
import MemoryPage from '../pages/MemoryPage'
import ProfilePage from '../pages/ProfilePage'
import PersonalAssistantPage from '../pages/PersonalAssistantPage'

export default function AppRouter(){return <BrowserRouter><Routes><Route path="/" element={<Navigate to="/assistant" replace/>}/><Route path="/login" element={<LoginPage/>}/><Route path="/register" element={<RegisterPage/>}/><Route element={<ProtectedRoute/>}><Route element={<AppLayout/>}><Route path="/assistant" element={<PersonalAssistantPage/>}/><Route path="/chat" element={<ChatPage/>}/><Route path="/tasks" element={<TaskPage/>}/><Route path="/calendar" element={<CalendarPage/>}/><Route path="/reminders" element={<ReminderPage/>}/><Route path="/memory" element={<MemoryPage/>}/><Route path="/profile" element={<ProfilePage/>}/></Route></Route><Route path="*" element={<Navigate to="/assistant" replace/>}/></Routes></BrowserRouter>}
